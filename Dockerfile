# Keep the Functions host and Python worker together; do not install azure-functions-worker.
ARG FUNCTIONS_BASE_IMAGE=mcr.microsoft.com/azure-functions/python:4-python3.14
FROM ${FUNCTIONS_BASE_IMAGE}

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    FUNCTIONS_WORKER_RUNTIME=python \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /home/site/wwwroot
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --target /home/site/wwwroot/.python_packages/lib/site-packages -r requirements.txt

COPY AIInteractionService ./AIInteractionService
COPY activities ./activities
COPY orchestrators ./orchestrators
COPY utils ./utils
COPY configs ./configs
COPY function_app.py search_api.py host.json ./
COPY deploy/start_functions.py /opt/aimie/start_functions.py

EXPOSE 80
ENTRYPOINT ["python", "/opt/aimie/start_functions.py"]
CMD ["/opt/startup/start_nonappservice.sh"]
