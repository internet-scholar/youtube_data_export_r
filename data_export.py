from internet_scholar import AthenaLogger, SqliteAWS, AthenaDatabase, compress
import sqlite3
import boto3
from datetime import date, timedelta, datetime
import logging

RECOMMENDATION = """
select
  youtube_related_video.creation_date recommendation_date,
  snippet_trending.id trending_video_id,
  snippet_trending.snippet.publishedAt trending_published_at,
  snippet_trending.snippet.channelId trending_channel_id,
  category_for_trending.title category_trending,
  snippet_recommended.id recommended_video_id,
  snippet_recommended.snippet.publishedAt recommended_published_at,
  snippet_recommended.snippet.channelId recommended_channel_id,
  category_for_recommended.title category_recommended,
  youtube_related_video.rank rank
from
  internet_scholar.youtube_related_video,
  internet_scholar.youtube_video_snippet as snippet_trending,
  internet_scholar.youtube_video_snippet as snippet_recommended,
  internet_scholar.youtube_category as category_for_trending,
  internet_scholar.youtube_category as category_for_recommended
where
  youtube_related_video.creation_date between '{begin_date}' and '{end_date}' and
  snippet_trending.id = youtube_related_video.relatedToVideoId and
  snippet_recommended.id = youtube_related_video.id.videoId and
  category_for_trending.id = coalesce(snippet_trending.snippet.categoryId, 'NULL') and
  category_for_recommended.id = coalesce(snippet_recommended.snippet.categoryId, 'NULL');
"""

CREATE_TABLE_RECOMMENDATION = """
CREATE TABLE recommendation (
  recommendation_date TEXT,
  trending_video_id TEXT,
  trending_published_at TEXT,
  trending_channel_id TEXT,
  category_trending TEXT,
  recommended_video_id TEXT,
  recommended_published_at TEXT,
  recommended_channel_id TEXT,
  category_recommended TEXT,
  rank INT,
  PRIMARY KEY (recommendation_date, trending_video_id, rank)
)
"""

INSERT_TABLE_RECOMMENDATION = """
INSERT INTO recommendation (recommendation_date, trending_video_id, trending_published_at,
                            trending_channel_id, category_trending, recommended_video_id,
                            recommended_published_at, recommended_channel_id, category_recommended, rank)
SELECT
    recommendation_date,
    trending_video_id,
    trending_published_at,
    trending_channel_id,
    category_trending,
    recommended_video_id,
    recommended_published_at,
    recommended_channel_id,
    category_recommended,
    rank
FROM recommendation_aux
"""

UPDATE_CATEGORY_TRENDING = """
update recommendation
set category_trending = NULL
where category_trending = 'Null Value'
"""

UPDATE_CATEGORY_RECOMMENDED = """
update recommendation
set category_recommended = NULL
where category_recommended = 'Null Value'
"""

TWITTER_USER_CHANNEL = """
SELECT DISTINCT
  tweet_user_url.user_id user_id,
  youtube_video_snippet.snippet.channelid channel_id,
  tweet_user_url.creation_date creation_date
FROM
  internet_scholar.tweet_user_url,
  internet_scholar.validated_url,
  internet_scholar.youtube_video_snippet
WHERE
  validated_url.url = tweet_user_url.url AND
  url_extract_host(validated_url.validated_url) = 'www.youtube.com' AND
  youtube_video_snippet.snippet.channelid IS NOT NULL AND
  url_extract_parameter(validated_url.validated_url, 'v') = youtube_video_snippet.id AND 
  tweet_user_url.creation_date between '{initial_date}' and '{final_date}'
"""

CREATE_YOUTUBE_CHANNEL_COMMON_TWITTER_USERS = """
create table if not exists youtube_channel_common_twitter_users (
  creation_date text,
  channel_1 text,
  channel_2 text,
  common_users_count int,
  primary key (creation_date, channel_1, channel_2)
)
"""

INSERT_YOUTUBE_CHANNEL_COMMON_TWITTER_USERS = """
insert into youtube_channel_common_twitter_users
(creation_date, channel_1, channel_2, common_users_count)
select
  '{final_date}',
  a.channel_id,
  b.channel_id,
  count(distinct a.user_id)
from
  twitter_user_channel a,
  twitter_user_channel b
where
  a.user_id = b.user_id and
  a.creation_date between '{initial_date}' and '{final_date}' and
  b.creation_date between '{initial_date}' and '{final_date}'
group by
  a.channel_id,
  b.channel_id;
"""

UPDATE_TRENDING_USER_COUNT = """
UPDATE recommendation
SET trending_user_count = (
    SELECT common_users_count
    FROM youtube_channel_common_twitter_users
    WHERE channel_1 = trending_channel_id and
          channel_2 = trending_channel_id and
          creation_date = recommendation_date
)
WHERE recommendation.trending_user_count IS NULL
"""

UPDATE_RECOMMENDED_USER_COUNT = """
UPDATE recommendation
SET recommended_user_count = (
    SELECT common_users_count
    FROM youtube_channel_common_twitter_users
    WHERE channel_1 = recommended_channel_id and
          channel_2 = recommended_channel_id and
          creation_date = recommendation_date
)
WHERE recommendation.recommended_user_count IS NULL
"""

UPDATE_COMMON_USER_COUNT = """
UPDATE recommendation
SET common_user_count = (
    SELECT common_users_count
    FROM youtube_channel_common_twitter_users
    WHERE channel_1 = trending_channel_id and
          channel_2 = recommended_channel_id and
          creation_date = recommendation_date
)
WHERE recommendation.common_user_count IS NULL
"""

SELECT_POLITICAL_LEANING = """
select
  youtube_graph_classification.related_date related_date,
  youtube_graph_classification.related_channel_id channel_id,
  case youtube_graph_classification.relationship
    when 'IDENTITY' then 'RIGHT'
    when 'KINSHIP'  then 'RIGHT'
    else 'LEFT'
  end political_leaning
from
  internet_scholar.youtube_graph_classification
where
  youtube_graph_classification.related_date between '{initial_date}' and '{final_date}' and
  youtube_graph_classification.graph_channel_id = 'UC8hGUtfEgvvnp6IaHSAg1OQ' and
  youtube_graph_classification.relationship in ('KINSHIP', 'IDENTITY', 'OPPOSITION')
"""

UPDATE_TRENDING_POLITICAL_LEANING = """
UPDATE recommendation
SET trending_political_leaning = (
    select
        channel_political_leaning.political_leaning
    from
        channel_political_leaning
    where
        recommendation.recommendation_date = channel_political_leaning.related_date and
        recommendation.trending_channel_id = channel_political_leaning.channel_id
    )
where recommendation.trending_political_leaning is null
"""

UPDATE_RECOMMENDED_POLITICAL_LEANING = """
UPDATE recommendation
SET recommended_political_leaning = (
    select
        channel_political_leaning.political_leaning
    from
        channel_political_leaning
    where
        recommendation.recommendation_date = channel_political_leaning.related_date and
        recommendation.recommended_channel_id = channel_political_leaning.channel_id
    )
where recommendation.recommended_political_leaning is null
"""

UPDATE_NULL_RECOMMENDED = """
UPDATE recommendation
SET recommended_published_at = null, recommended_channel_id = null
WHERE recommended_published_at = '' and recommended_channel_id = ''
"""

UPDATE_NULL_TRENDING = """
UPDATE recommendation
SET trending_published_at = null, trending_channel_id = null
where trending_channel_id = '' and trending_published_at = ''
"""

CREATE_VIEW_ENHANCED_CHANNEL_STATS = """
create or replace view youtube_enhanced_channel_stats as
select
  creation_date,
  id as channel_id,
  if(statistics.viewcount - lag(statistics.viewcount, 1, statistics.viewcount)
        over (partition by id order by creation_date) > 0,
     statistics.viewcount - lag(statistics.viewcount, 1, statistics.viewcount)
        over (partition by id order by creation_date), 0) as view_count,
  statistics.viewcount as cumulative_view_count,
  if(statistics.subscribercount - lag(statistics.subscribercount, 1, statistics.subscribercount)
        over (partition by id order by creation_date) > 0,
     statistics.subscribercount - lag(statistics.subscribercount, 1, statistics.subscribercount)
        over (partition by id order by creation_date), 0) as subscriber_count,
  statistics.subscribercount as cumulative_subscriber_count,
  if(statistics.videocount - lag(statistics.videocount, 1, statistics.videocount)
        over (partition by id order by creation_date) > 0,
     statistics.videocount - lag(statistics.videocount, 1, statistics.videocount)
        over (partition by id order by creation_date), 0) as video_count,
  statistics.videocount as cumulative_video_count,
  if(statistics.commentcount - lag(statistics.commentcount, 1, statistics.commentcount)
        over (partition by id order by creation_date) > 0,
     statistics.commentcount - lag(statistics.commentcount, 1, statistics.commentcount)
        over (partition by id order by creation_date), 0) as comment_count,
  statistics.commentcount as cumulative_comment_count
from
  youtube_channel_stats
"""

SELECT_ENHANCED_STATS = """
select
  creation_date,
  channel_id,
  view_count,
  cumulative_view_count,
  subscriber_count,
  cumulative_subscriber_count,
  video_count,
  cumulative_video_count,
  comment_count,
  cumulative_comment_count
from
  internet_scholar.youtube_enhanced_channel_stats
where
  creation_date between '{initial_date}' and '{final_date}'
"""

CREATE_CHANNEL_STATS_WITH_PRIMARY_KEY = """
create table channel_stats_with_primary_key (
    creation_date TEXT,
    channel_id TEXT,
    view_count INT,
    cumulative_view_count INT,
    subscriber_count INT,
    cumulative_subscriber_count INT,
    video_count INT,
    cumulative_video_count INT,
    comment_count INT,
    cumulative_comment_count INT,
    primary key (creation_date, channel_id)
)
"""

INSERT_CHANNEL_STATS_WITH_PRIMARY_KEY = """
insert into channel_stats_with_primary_key
  (creation_date, channel_id, view_count, cumulative_view_count,
  subscriber_count, cumulative_subscriber_count, video_count,
  cumulative_video_count, comment_count, cumulative_comment_count)
select
  creation_date, channel_id, view_count, cumulative_view_count,
  subscriber_count, cumulative_subscriber_count, video_count,
  cumulative_video_count, comment_count, cumulative_comment_count
from channel_stats
"""

UPDATE_STAT_RECOMMENDED = """
update recommendation
set recommended_{field} = (
    select channel_stats_with_primary_key.{field}
    from channel_stats_with_primary_key
    where channel_stats_with_primary_key.channel_id = recommendation.recommended_channel_id and
          channel_stats_with_primary_key.creation_date = recommendation.recommendation_date
    )
where recommended_{field} is null
"""

UPDATE_STAT_TRENDING = """
update recommendation
set trending_{field} = (
    select channel_stats_with_primary_key.{field}
    from channel_stats_with_primary_key
    where channel_stats_with_primary_key.channel_id = recommendation.trending_channel_id and
          channel_stats_with_primary_key.creation_date = recommendation.recommendation_date
    )
where trending_{field} is null
"""


def add_stat_to_sqlite(database, field):
    logging.info('Add stat {field}...'.format(field=field))
    database.execute("ALTER TABLE recommendation ADD COLUMN trending_{field} INT".format(field=field))
    database.execute(UPDATE_STAT_TRENDING.format(field=field))
    database.execute("ALTER TABLE recommendation ADD COLUMN recommended_{field} INT".format(field=field))
    database.execute(UPDATE_STAT_RECOMMENDED.format(field=field))


def import_data(related_date, end_related_date, graph_date_difference, timespan):
    database = sqlite3.connect('./youtube_recommendations.sqlite')
    sqlite_aws = SqliteAWS(database=database,
                           s3_admin='internet-scholar-admin',
                           s3_data='internet-scholar',
                           athena_db='internet_scholar')
    logging.info('Retrieve recommendations...')
    sqlite_aws.convert_athena_query_to_sqlite(table_name='recommendation_aux',
                                              query=RECOMMENDATION.format(begin_date=str(related_date),
                                                                          end_date=str(end_related_date)))

    logging.info('Add primary key to recommendation table...')
    database.execute(CREATE_TABLE_RECOMMENDATION)
    database.execute(INSERT_TABLE_RECOMMENDATION)
    database.execute('DROP TABLE recommendation_aux')
    logging.info('Update categories and null values...')
    database.execute(UPDATE_CATEGORY_TRENDING)
    database.execute(UPDATE_CATEGORY_RECOMMENDED)
    database.execute(UPDATE_NULL_TRENDING)
    database.execute(UPDATE_NULL_RECOMMENDED)

    logging.info('Retrieve Twitter users and YouTube channel data...')
    initial_date = related_date + timedelta(days=graph_date_difference) - timedelta(days=timespan-1)
    final_date = end_related_date + timedelta(days=graph_date_difference)
    sqlite_aws.convert_athena_query_to_sqlite(table_name='twitter_user_channel',
                                              query=TWITTER_USER_CHANNEL.format(initial_date=str(initial_date),
                                                                                final_date=str(final_date)))

    logging.info('Calculate number of common Twitter users per channel...')
    database.execute(CREATE_YOUTUBE_CHANNEL_COMMON_TWITTER_USERS)
    current_date = related_date
    while current_date <= end_related_date:
        logging.info(str(current_date))
        initial_date = current_date + timedelta(days=graph_date_difference) - timedelta(days=timespan - 1)
        final_date = current_date + timedelta(days=graph_date_difference)
        database.execute(INSERT_YOUTUBE_CHANNEL_COMMON_TWITTER_USERS.format(initial_date=initial_date,
                                                                            final_date=final_date))
        current_date = current_date + timedelta(days=1)
    logging.info('Update aggregate on SQLite table 1...')
    database.execute("ALTER TABLE recommendation ADD COLUMN trending_user_count INT")
    database.execute(UPDATE_TRENDING_USER_COUNT)
    logging.info('Update aggregate on SQLite table 2...')
    database.execute("ALTER TABLE recommendation ADD COLUMN recommended_user_count INT")
    database.execute(UPDATE_RECOMMENDED_USER_COUNT)
    logging.info('Update aggregate on SQLite table 3...')
    database.execute("ALTER TABLE recommendation ADD COLUMN common_user_count INT")
    database.execute(UPDATE_COMMON_USER_COUNT)

    logging.info('Retrieve info about political leaning...')
    sqlite_aws.convert_athena_query_to_sqlite(table_name='channel_political_leaning',
                                              query=SELECT_POLITICAL_LEANING.format(initial_date=str(related_date),
                                                                                    final_date=str(end_related_date)))
    logging.info('Update political leaning info on SQLite 1...')
    database.execute("ALTER TABLE recommendation ADD COLUMN trending_political_leaning TEXT")
    database.execute(UPDATE_TRENDING_POLITICAL_LEANING)
    logging.info('Update political leaning info on SQLite 1...')
    database.execute("ALTER TABLE recommendation ADD COLUMN recommended_political_leaning TEXT")
    database.execute(UPDATE_RECOMMENDED_POLITICAL_LEANING)

    logging.info('Retrieve data on channel stats...')
    athena_db = AthenaDatabase(database='internet_scholar', s3_output='internet-scholar-admin')
    athena_db.query_athena_and_wait(query_string=CREATE_VIEW_ENHANCED_CHANNEL_STATS)
    sqlite_aws.convert_athena_query_to_sqlite(table_name='channel_stats',
                                              query=SELECT_ENHANCED_STATS.format(initial_date=str(related_date),
                                                                                 final_date=str(end_related_date)))
    logging.info('Add primary key to channel stats...')
    database.execute(CREATE_CHANNEL_STATS_WITH_PRIMARY_KEY)
    database.execute(INSERT_CHANNEL_STATS_WITH_PRIMARY_KEY)
    add_stat_to_sqlite(database, field='view_count')
    add_stat_to_sqlite(database, field='cumulative_view_count')
    add_stat_to_sqlite(database, field='subscriber_count')
    add_stat_to_sqlite(database, field='cumulative_subscriber_count')
    add_stat_to_sqlite(database, field='video_count')
    add_stat_to_sqlite(database, field='cumulative_video_count')
    add_stat_to_sqlite(database, field='comment_count')
    add_stat_to_sqlite(database, field='cumulative_comment_count')

    database.execute('DROP TABLE channel_political_leaning')
    database.execute('DROP TABLE channel_stats')
    database.execute('DROP TABLE channel_stats_with_primary_key')
    database.execute('DROP TABLE twitter_user_channel')
    database.execute('DROP TABLE youtube_channel_common_twitter_users')
    database.commit()

    database.execute('VACUUM')
    database.close()

    new_filename = compress('./youtube_recommendations.sqlite')
    s3_filename = "youtube_data_export_r/{timestamp}.sqlite.bz2".format(
        timestamp=datetime.utcnow().strftime("%Y%m%d-%H%M%S"))
    s3 = boto3.resource('s3')
    s3.Bucket('internet-scholar').upload_file(str(new_filename), s3_filename)


def main():
    logger = AthenaLogger(app_name="youtube_data_export_r",
                          s3_bucket='internet-scholar-admin',
                          athena_db='internet_scholar_admin')
    try:
        import_data(related_date=date(2019, 10, 20),
                    end_related_date=date(2020, 2, 20),
                    graph_date_difference=0,
                    timespan=60)
    finally:
        logger.save_to_s3()
        # logger.recreate_athena_table()


if __name__ == '__main__':
    main()
