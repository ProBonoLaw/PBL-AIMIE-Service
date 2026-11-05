# Appended to function_app.py ONLY in the disposable container smoke test.
# No model calls or application data stores are used by this workflow.
from datetime import timedelta


@app.orchestration_trigger(context_name="context", orchestration="AksSmokeOrchestration")
def aks_smoke_orchestration(context: df.DurableOrchestrationContext):
    output = yield context.call_activity("aksSmokeActivity", "persisted activity result")
    context.set_custom_status("waiting-for-restart")
    yield context.create_timer(context.current_utc_datetime + timedelta(seconds=45))
    return output


@app.activity_trigger(input_name="value", activity="aksSmokeActivity")
def aks_smoke_activity(value: str):
    return value


@app.route(route="_aks_smoke", methods=["POST"])
@app.durable_client_input(client_name="client")
async def aks_smoke_start(req: func.HttpRequest, client: df.DurableOrchestrationClient):
    instance = await client.start_new("AksSmokeOrchestration")
    return client.create_check_status_response(req, instance)
