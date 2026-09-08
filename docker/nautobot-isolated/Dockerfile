FROM networktocode/nautobot:2.2-py3.11

USER 0
COPY local_requirements.txt /tmp/local_requirements.txt
RUN pip install --no-cache-dir -r /tmp/local_requirements.txt
USER nautobot
