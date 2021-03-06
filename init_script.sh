#!/bin/bash
# suggested AWS EC2 instance: t3a.medium
sudo timedatectl set-timezone UTC
sudo apt update -y
sudo apt install -y python3-pip
cd /home/ubuntu
wget https://raw.githubusercontent.com/internet-scholar/youtube_data_export_r/master/requirements.txt
wget https://raw.githubusercontent.com/internet-scholar/youtube_data_export_r/master/data_export.py
wget https://raw.githubusercontent.com/internet-scholar/internet_scholar/master/requirements.txt -O requirements2.txt
wget https://raw.githubusercontent.com/internet-scholar/internet_scholar/master/internet_scholar.py
pip3 install --trusted-host pypi.python.org -r /home/ubuntu/requirements.txt
pip3 install --trusted-host pypi.python.org -r /home/ubuntu/requirements2.txt
mkdir .aws
printf "[default]\\nregion=us-west-2" > /home/ubuntu/.aws/config
python3 /home/ubuntu/data_export.py && sudo shutdown -h now