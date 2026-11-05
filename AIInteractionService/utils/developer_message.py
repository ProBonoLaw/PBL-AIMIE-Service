from typing import Any, Literal, Union

from langchain_core.messages.base import BaseMessage, BaseMessageChunk


class DeveloperMessage(BaseMessage):
    """Message for priming AI behavior.

    The developer message is usually passed in as the first of a sequence
    of input messages.

    Example:

        .. code-block:: python

            from langchain_core.messages import HumanMessage, DeveloperMessage

            messages = [
                DeveloperMessage(
                    content="You are a helpful assistant! Your name is Bob."
                ),
                HumanMessage(
                    content="What is your name?"
                )
            ]

            # Define a chat model and invoke it with the messages
            print(model.invoke(messages))

    """

    type: Literal["developer"] = "developer"
    """The type of the message (used for serialization). Defaults to "developer"."""

    @classmethod
    def get_lc_namespace(cls) -> list[str]:
        """Get the namespace of the langchain object.
        Default is ["langchain", "schema", "messages"].
        """
        return ["langchain", "schema", "messages"]

    def __init__(
        self, content: Union[str, list[Union[str, dict]]], **kwargs: Any
    ) -> None:
        """Pass in content as positional arg.

        Args:
               content: The string contents of the message.
               kwargs: Additional fields to pass to the message.
        """
        super().__init__(content=content, **kwargs)


DeveloperMessage.model_rebuild()


class DeveloperMessageChunk(DeveloperMessage, BaseMessageChunk):
    """System Message chunk."""

    # Ignoring mypy re-assignment here since we're overriding the value
    # to make sure that the chunk variant can be discriminated from the
    # non-chunk variant.
    type: Literal["DeveloperMessageChunk"] = "DeveloperMessageChunk"
    """The type of the message (used for serialization).
    Defaults to "DeveloperMessageChunk"."""

    @classmethod
    def get_lc_namespace(cls) -> list[str]:
        """Get the namespace of the langchain object.
        Default is ["langchain", "schema", "messages"].
        """
        return ["langchain", "schema", "messages"]
