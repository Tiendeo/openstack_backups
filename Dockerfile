FROM ismaelperal/python-openstackclient:3.19.0

WORKDIR /app
COPY ./src/* .
CMD [ "python", "create-image.py", "--help" ]
