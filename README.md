# Ranger-bot

Slack bot to give you insight on your AWS account

## Build

`docker build . -t ranger-bot`

## Run

`docker run -d -e AWS_ACCESS_KEY_ID="" \
-e AWS_SECRET_ACCESS_KEY="" \
-e SLACK_BOT_TOKEN="" \
-e SLACK_SIGNING_SECRET="" -p 8080:3000 ranger-bot`


