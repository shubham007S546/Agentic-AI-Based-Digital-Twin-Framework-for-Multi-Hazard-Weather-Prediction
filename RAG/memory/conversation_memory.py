# chat memory or short term memory
from collections import deque


class ConversationMemory:

    def __init__(self, max_messages=10):

        self.history = deque(maxlen=max_messages)

    def add_user_message(self, message):

        self.history.append({

            "role": "user",

            "content": message

        })

    def add_assistant_message(self, message):

        self.history.append({

            "role": "assistant",

            "content": message

        })

    def get_context(self):

        context = ""

        for message in self.history:

            context += (

                f"{message['role'].title()}: "

                f"{message['content']}\n\n"

            )

        return context

    def clear(self):

        self.history.clear()