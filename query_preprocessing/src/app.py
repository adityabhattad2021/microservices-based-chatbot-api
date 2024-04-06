from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import requests
from .redis_manager import get_redis_manager
from .chat_summary_manager import get_chat_summary_manager
from pydantic import BaseModel
import google.generativeai as genai
from langchain.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import find_dotenv, load_dotenv
import os
import json

load_dotenv(find_dotenv())
# genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

app = FastAPI(root_path="/api/chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class Message(BaseModel):
    conversation_id:str
    content:str

@app.get("/")
def root():
    return {"message":"hello from query_preprocessing_service"}



def is_relevant(message: str):
    
    llm = GoogleGenerativeAI(model="gemini-pro", google_api_key=os.getenv("GOOGLE_API_KEY"))

    template = """
        You are an AI just built to classify queries as medical or not. 
        Your job is to identify medical words and also whether the given sentence makes any sense that requires any medical treatment or not.
        Find important medical keywords from query and check whether it makes any sense of medical field.s
        You can only give output in 3 words: 1)YES, 2)NO, 3)MAYBE, except these 3 words you won't output anything.
        You job is to return a response , just return 'YES', 'NO' or 'MAYBE'.
        If you don't know what is the answer, just return 'MAYBE' as your response else return your answer.
        Query: {query}
    """
    prompt = PromptTemplate.from_template(template)

    chain = prompt | llm

    response = chain.invoke({"query": str(message)})
    # response = json.loads(response)

    if response == "NO":
        return False
    else:
        return True

@app.post('/generate')
def get_ai_message(req_body:Message):

    response = is_relevant(req_body.content)

    if not response:
        return {"ai_response":"Irrelevent question. It is not related to medical field by any sense."}

    
    print(f"{response=}")

    chat_manager = get_redis_manager(req_body.conversation_id)
    chat_history = chat_manager.get_messages()
    summary_manager = get_chat_summary_manager(temperature=0.2)

    # Generate a standalone query for question answer service.
    query=summary_manager.generate_query(chats=chat_history,new_query=req_body.content)
    try:
        response = requests.post(
            f'http://qa-service:8000/get-ai-response',
            json={"query": query}
        )
        response.raise_for_status()
        ai_response = response.json()
    except requests.exceptions.RequestException as e:
        chat_manager.add_user_message(req_body.content)
        return {"error": f"Request to qa_service failed: {e}"}
    else:
        chat_manager.add_user_message(req_body.content)
        chat_manager.add_ai_message(ai_response.get('ai_response'))
        return {"ai_response":ai_response.get("ai_response")}

## I will test it when frontend is ready, till then donot use

# @app.post('/generate')
# def get_ai_message(req_body: Message):
#     return StreamingResponse(gen_streaming_response(req_body))

# def gen_streaming_response(req_body:Message):
#     chat_manager = get_redis_manager(req_body.conversation_id)
#     chat_history = chat_manager.get_messages()
#     summary_manager = get_chat_summary_manager(temperature=0.2)

#     # Generate a standalone query for question answer service.
#     query=summary_manager.generate_query(chats=chat_history,new_query=req_body.content)
#     try:
#         response = requests.post(
#             f'http://qa-service:8000/get-ai-response',
#             json={"query": query}
#         )
#         response.raise_for_status()
#         ai_response = response.json()
#     except requests.exceptions.RequestException as e:
#         chat_manager.add_user_message(req_body.content)
#         yield {"error": f"Request to qa_service failed: {e}"}
#     else:
#         chat_manager.add_user_message(req_body.content)
#         chat_manager.add_ai_message(ai_response.get('ai_response'))
#         yield {"ai_response":ai_response.get("ai_response")}
    