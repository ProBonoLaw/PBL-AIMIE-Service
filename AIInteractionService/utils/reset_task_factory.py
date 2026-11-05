import asyncio

class ResetTaskFactory:
    def __enter__(self):
        self.loop = asyncio.get_running_loop()
        self.old_factory = self.loop.get_task_factory()
        self.loop.set_task_factory(None)  # Reset to default

    def __exit__(self, exc_type, exc_value, traceback):
        self.loop.set_task_factory(self.old_factory)
