FROM python:3.6
ENV PYTHONUNBUFFERED 1
RUN mkdir /bot
WORKDIR /bot
ADD requirements.txt /bot/
RUN pip install -r requirements.txt
ADD . /bot/