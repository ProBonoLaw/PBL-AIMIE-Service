import os
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.langchain import LangchainInstrumentor


def enable_instrumentation():
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    configure_azure_monitor(connection_string=connection_string)
