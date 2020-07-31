FROM fnndsc/ubuntu-python3

ENV AWS_ACCESS_KEY_ID=''
ENV AWS_SECRET_ACCESS_KEY=''

ENV SLACK_BOT_TOKEN=''
ENV SLACK_SIGNING_SECRET=''

COPY source/*.py /opt/
COPY source/requirements.txt /opt/

RUN pip install -r /opt/requirements.txt

CMD ["/opt/app.py"]

ENTRYPOINT ["python3"]