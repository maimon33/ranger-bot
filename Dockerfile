FROM fnndsc/ubuntu-python3

ENV SLACK_BOT_TOKEN='xoxb-1234849473364-1275209257156-sDDUSMtNYnh7fFK6riKJ3pQc'
ENV SLACK_SIGNING_SECRET='7888ad489e320e28f1b6fe5a714df32b'

COPY source/*.py /opt/
COPY source/requirements.txt /opt/

RUN pip install -r /opt/requirements.txt

CMD ["/opt/app.py"]

ENTRYPOINT ["python3"]