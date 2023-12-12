import streamlit as st

from langchain.embeddings import OpenAIEmbeddings
from langchain.callbacks import StreamlitCallbackHandler
from langchain.agents import OpenAIFunctionsAgent, AgentExecutor
from langchain.agents.agent_toolkits import create_retriever_tool
from langchain.agents.openai_functions_agent.agent_token_buffer_memory import (
    AgentTokenBufferMemory,
)
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, AIMessage, HumanMessage
from langchain.prompts import MessagesPlaceholder

from langsmith import Client

# --
from langchain.vectorstores import Qdrant
from qdrant_client import QdrantClient
from conf.constants import *


client = Client()

st.set_page_config(
    page_title="Camel Quickstart Assitant",
    page_icon="🦜",
    layout="wide",
    initial_sidebar_state="collapsed",
)

"# Camel Quickstart Assitant"

def create_qdrant_client(): 
    client = QdrantClient(
       QDRANT_URL,
        api_key=QDRANT_KEY,
    )
    return client

@st.cache_resource(ttl="1h")
def configure_retriever(collection_name):
    
    qdrant = Qdrant(
        client=create_qdrant_client(), 
        collection_name=collection_name, 
        embeddings=OpenAIEmbeddings())
    
    # top k and threshold settings see https://python.langchain.com/docs/modules/data_connection/retrievers/vectorstore
    return qdrant.as_retriever() 

comp_ref_tool = create_retriever_tool(
    configure_retriever("agent_fuse_comp_ref"),
    "search_camel_component_reference",
    "Searches and returns documents regarding Camel Components and their configuration options. Camel Components are used within the Camel framework to integrate third-party systems",
)

tools = [comp_ref_tool]
llm = ChatOpenAI(temperature=0, streaming=True, model="gpt-3.5-turbo-1106")
message = SystemMessage(
    content=(
        "You are an assistant helping software developers create integrations with third-party systems using the Apache Camel framework."
        "Unless otherwise explicitly stated, it is probably fair to assume that questions are about Apache Camel. "
        "If there is any ambiguity, you probably assume they are about that."
        "If possible, provide examples that include Java code within the response."
    )
)
prompt = OpenAIFunctionsAgent.create_prompt(
    system_message=message,
    extra_prompt_messages=[MessagesPlaceholder(variable_name="history")],
)
agent = OpenAIFunctionsAgent(llm=llm, tools=tools, prompt=prompt) # TODO: does it support a `max_iterations` parameter?
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    return_intermediate_steps=True,
)
memory = AgentTokenBufferMemory(llm=llm)
starter_message = "Ask me anything about Camel!"
if "messages" not in st.session_state or st.sidebar.button("Clear message history"):
    st.session_state["messages"] = [AIMessage(content=starter_message)]


def send_feedback(run_id, score):
    print(str(run_id), str(score))
    #client.create_feedback(run_id, "user_score", score=score)


for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant").write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user").write(msg.content)
    memory.chat_memory.add_message(msg)


if prompt := st.chat_input(placeholder=starter_message):
    st.chat_message("user").write(prompt)
    with st.chat_message("assistant"):
        st_callback = StreamlitCallbackHandler(
            parent_container=st.container(),
            collapse_completed_thoughts=False
            )
        response = agent_executor(
            {"input": prompt, "history": st.session_state.messages},
            callbacks=[st_callback],
            include_run_info=True,
        )
        st.session_state.messages.append(AIMessage(content=response["output"]))
        st.write(response["output"])
        memory.save_context({"input": prompt}, response)
        st.session_state["messages"] = memory.buffer
        run_id = response["__run"].run_id

        col_blank, col_text, col1, col2 = st.columns([10, 2, 1, 1])
        with col_text:
            st.text("Feedback:")

        with col1:
            st.button("👍", on_click=send_feedback, args=(run_id, 1))

        with col2:
            st.button("👎", on_click=send_feedback, args=(run_id, 0))