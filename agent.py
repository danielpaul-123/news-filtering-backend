params = {
    "space_id": "2eb7cafe-8f67-4fb1-8334-425bc268e428", 
}
def gen_ai_service(context, params = params, **custom):
    # import dependencies
    from langchain_ibm import ChatWatsonx
    from ibm_watsonx_ai import APIClient
    from ibm_watsonx_ai.foundation_models.utils import Tool, Toolkit
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent
    import json
    import requests
    model = "meta-llama/llama-3-2-90b-vision-instruct"
    service_url = "https://us-south.ml.cloud.ibm.com"
    # Get credentials token
    credentials = {
        "url": service_url,
        "token": context.generate_token()
    }
    # Setup client
    client = APIClient(credentials)
    space_id = params.get("space_id")
    client.set.default_space(space_id)
    def decrypt_tool_secrets(secrets):
        url = "https://api.dataplatform.cloud.ibm.com"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f'Bearer {context.generate_token()}'
        }
        body = {
            "secrets": secrets,
            "space_id": space_id
        }
        response = requests.post(f'{url}/wx/v1-beta/utility_agent_tools/secret/decrypt', headers=headers, json=body)
        return response.json().get("secrets")
    encrypted_secrets = [
        "gcm-agent-tools-qHi31me0EfjVZVuGAnau05GBdpyvCVyV:wyyYheIiOjHQZR309UZovw==;9dLU9lptLOIv3jGr3EN46A==:vWpET59PqgZI95wuoHWaxBdgBhIBd8LbbMFOapWy7ve1M5NLzjzGyL0="
    ]
    decrypted_secrets = decrypt_tool_secrets(encrypted_secrets)
    TavilySearch_apiKey = decrypted_secrets[0]
    def create_chat_model(watsonx_client):
        parameters = {
            "frequency_penalty": 0,
            "max_tokens": 2000,
            "presence_penalty": 0,
            "temperature": 0,
            "top_p": 1
        }
        chat_model = ChatWatsonx(
            model_id=model,
            url=service_url,
            space_id=space_id,
            params=parameters,
            watsonx_client=watsonx_client,
        )
        return chat_model
    def create_utility_agent_tool(tool_name, params, api_client, **kwargs):
        from langchain_core.tools import StructuredTool
        utility_agent_tool = Toolkit(
            api_client=api_client
        ).get_tool(tool_name)
        tool_description = utility_agent_tool.get("description")
        if (kwargs.get("tool_description")):
            tool_description = kwargs.get("tool_description")
        elif (utility_agent_tool.get("agent_description")):
            tool_description = utility_agent_tool.get("agent_description")
        tool_schema = utility_agent_tool.get("input_schema")
        if (tool_schema == None):
            tool_schema = {
                "type": "object",
                "additionalProperties": False,
                "$schema": "http://json-schema.org/draft-07/schema#",
                "properties": {
                    "input": {
                        "description": "input for the tool",
                        "type": "string"
                    }
                }
            }
        def run_tool(**tool_input):
            query = tool_input
            if (utility_agent_tool.get("input_schema") == None):
                query = tool_input.get("input")
            results = utility_agent_tool.run(
                input=query,
                config=params
            )
            return results.get("output")
        return StructuredTool(
            name=tool_name,
            description = tool_description,
            func=run_tool,
            args_schema=tool_schema
        )
    def create_custom_tool(tool_name, tool_description, tool_code, tool_schema, tool_params):
        from langchain_core.tools import StructuredTool
        import ast
        def call_tool(**kwargs):
            tree = ast.parse(tool_code, mode="exec")
            custom_tool_functions = [ x for x in tree.body if isinstance(x, ast.FunctionDef) ]
            function_name = custom_tool_functions[0].name
            compiled_code = compile(tree, 'custom_tool', 'exec')
            namespace = tool_params if tool_params else {}
            exec(compiled_code, namespace)
            return namespace[function_name](**kwargs)
        tool = StructuredTool(
            name=tool_name,
            description = tool_description,
            func=call_tool,
            args_schema=tool_schema
        )
        return tool
    def create_custom_tools():
        custom_tools = []
    def create_tools(inner_client, context):
        tools = []
        config = None
        tools.append(create_utility_agent_tool("GoogleSearch", config, inner_client))
        config = {
        }
        tools.append(create_utility_agent_tool("DuckDuckGo", config, inner_client))
        config = {
            "maxResults": 5
        }
        tools.append(create_utility_agent_tool("Wikipedia", config, inner_client))
        config = {
            "maxResults": 10,
            "apiKey": TavilySearch_apiKey
        }
        tools.append(create_utility_agent_tool("TavilySearch", config, inner_client))
        config = {
        }
        tools.append(create_utility_agent_tool("WebCrawler", config, inner_client))
        return tools
    def create_agent(model, tools, messages):
        memory = MemorySaver()
        instructions = """# Notes
- Use markdown syntax for formatting code snippets, links, JSON, tables, images, files.
- Any HTML tags must be wrapped in block quotes, for example ```<html>```.
- When returning code blocks, specify language.
- Sometimes, things don't go as planned. Tools may not provide useful information on the first few tries. You should always try a few different approaches before declaring the problem unsolvable.
- When the tool doesn't give you what you were asking for, you must either use another tool or a different tool input.
- When using search engines, you try different formulations of the query, possibly even in a different language.
- You cannot do complex calculations, computations, or data manipulations without using tools.
- If you need to call a tool to compute something, always call it instead of saying you will call it.
If a tool returns an IMAGE in the result, you must include it in your answer as Markdown.
Example:
Tool result: IMAGE({commonApiUrl}/wx/v1-beta/utility_agent_tools/cache/images/plt-04e3c91ae04b47f8934a4e6b7d1fdc2c.png)
Markdown to return to user: ![Generated image]({commonApiUrl}/wx/v1-beta/utility_agent_tools/cache/images/plt-04e3c91ae04b47f8934a4e6b7d1fdc2c.png)
You are \"Edward\", an AI agent that verifies news claims for users. You are connected to:
- Google Search
- DuckDuckGo Search
- Wikipedia Search
- Tavily Search
- Webcrawler
INSTRUCTIONS:
1. Always use ALL connected search tools for every query.
2. Prioritize news sources from all states of India. If sufficient evidence is not available from Indian sources, use credible global sources.
3. Check for the LATEST news — compare each article's published date against the current date, and give higher weight to the most recent updates.
4. When searching, cover multiple Indian states and their major credible outlets. Use official government portals and verified press releases when available.
5. Use global credible outlets as fallback sources when Indian coverage is insufficient.
6. Your answer must be in the following format:
   - Result: \"True\", \"False\", or \"Inconclusive\"
   - Confidence: XX%
   - Reasoning: Short explanation of how you arrived at the decision.
   - Sources: List of all URLs used, grouped by state or \"Global\".
7. Use factual, unbiased language. Do not speculate.
8. If the news is still developing, mark as \"Inconclusive\".
9. Confidence % should reflect the strength of evidence and source credibility.
INDIAN STATE-WISE SOURCES:
Andhra Pradesh – The Hindu (AP edition), Eenadu, Sakshi  
Arunachal Pradesh – Arunachal Times, Echo of Arunachal  
Assam – The Assam Tribune, The Sentinel Assam  
Bihar – Hindustan (Hindi), Prabhat Khabar (Bihar edition)  
Chhattisgarh – The Hitavada, Deshbandhu  
Goa – O Heraldo, The Navhind Times  
Gujarat – Sandesh, Gujarat Samachar  
Haryana – Dainik Bhaskar (Haryana edition), The Tribune  
Himachal Pradesh – Divya Himachal, Himachal Watcher  
Jharkhand – Prabhat Khabar (Jharkhand edition), Dainik Jagran (Jharkhand)  
Karnataka – Deccan Herald, Prajavani  
Kerala – Malayala Manorama, Mathrubhumi  
Madhya Pradesh – Nai Duniya, Dainik Bhaskar (MP edition)  
Maharashtra – Lokmat, Maharashtra Times  
Manipur – The Sangai Express, Imphal Free Press  
Meghalaya – The Shillong Times, Meghalaya Times  
Mizoram – The Mizoram Post, Vanglaini  
Nagaland – Nagaland Post, Eastern Mirror Nagaland  
Odisha – Sambad, Dharitri  
Punjab – Ajit (Punjabi), The Tribune (Punjab)  
Rajasthan – Rajasthan Patrika, Dainik Bhaskar (Rajasthan)  
Sikkim – Sikkim Express, Summit Times  
Tamil Nadu – The Hindu (Tamil Nadu edition), Daily Thanthi  
Telangana – Telangana Today, Namasthe Telangana  
Tripura – Tripura Times, Daily Desher Katha  
Uttar Pradesh – Amar Ujala, Dainik Jagran (UP edition)  
Uttarakhand – Kumaon Vani, Amar Ujala (Uttarakhand edition)  
West Bengal – Anandabazar Patrika, The Telegraph  
GLOBAL CREDIBLE SOURCES:
BBC News, Reuters, Associated Press (AP), Al Jazeera, The Guardian, The New York Times, The Washington Post, CNN, The Economist, Bloomberg, Financial Times, DW News.
EXAMPLE RESPONSES:
Example 1 — TRUE:
Result: True  
Confidence: 92%  
Reasoning: Multiple recent articles from The Hindu, NDTV, and BBC confirm the news within the past 12 hours. All sources are consistent and credible.  
Sources:  
- Andhra Pradesh: https://www.thehindu.com/...  
- Global: https://www.bbc.com/...
Example 2 — FALSE:
Result: False  
Confidence: 87%  
Reasoning: No credible Indian or global outlet has published this news. Fact-checking sites and government press releases contradict the claim.  
Sources:  
- Kerala: https://www.mathrubhumi.com/...  
- Global: https://www.reuters.com/...
Example 3 — INCONCLUSIVE:
Result: Inconclusive  
Confidence: 55%  
Reasoning: Conflicting reports found. Some regional papers report the event, but no confirmation from major national or global outlets. News is less than 2 hours old, may still be developing.  
Sources:  
- Maharashtra: https://www.lokmat.com/...  
- Global: https://www.aljazeera.com/...
"""
        for message in messages:
            if message["role"] == "system":
                instructions += message["content"]
        graph = create_react_agent(model, tools=tools, checkpointer=memory, state_modifier=instructions)
        return graph
    def convert_messages(messages):
        converted_messages = []
        for message in messages:
            if (message["role"] == "user"):
                converted_messages.append(HumanMessage(content=message["content"]))
            elif (message["role"] == "assistant"):
                converted_messages.append(AIMessage(content=message["content"]))
        return converted_messages
    def generate(context):
        payload = context.get_json()
        messages = payload.get("messages")
        inner_credentials = {
            "url": service_url,
            "token": context.get_token()
        }
        inner_client = APIClient(inner_credentials)
        model = create_chat_model(inner_client)
        tools = create_tools(inner_client, context)
        agent = create_agent(model, tools, messages)
        generated_response = agent.invoke(
            { "messages": convert_messages(messages) },
            { "configurable": { "thread_id": "42" } }
        )
        last_message = generated_response["messages"][-1]
        generated_response = last_message.content
        execute_response = {
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "choices": [{
                    "index": 0,
                    "message": {
                       "role": "assistant",
                       "content": generated_response
                    }
                }]
            }
        }
        return execute_response
    def generate_stream(context):
        print("Generate stream", flush=True)
        payload = context.get_json()
        headers = context.get_headers()
        is_assistant = headers.get("X-Ai-Interface") == "assistant"
        messages = payload.get("messages")
        inner_credentials = {
            "url": service_url,
            "token": context.get_token()
        }
        inner_client = APIClient(inner_credentials)
        model = create_chat_model(inner_client)
        tools = create_tools(inner_client, context)
        agent = create_agent(model, tools, messages)
        response_stream = agent.stream(
            { "messages": messages },
            { "configurable": { "thread_id": "42" } },
            stream_mode=["updates", "messages"]
        )
        for chunk in response_stream:
            chunk_type = chunk[0]
            finish_reason = ""
            usage = None
            if (chunk_type == "messages"):
                message_object = chunk[1][0]
                if (message_object.type == "AIMessageChunk" and message_object.content != ""):
                    message = {
                        "role": "assistant",
                        "content": message_object.content
                    }
                else:
                    continue
            elif (chunk_type == "updates"):
                update = chunk[1]
                if ("agent" in update):
                    agent = update["agent"]
                    agent_result = agent["messages"][0]
                    if (agent_result.additional_kwargs):
                        kwargs = agent["messages"][0].additional_kwargs
                        tool_call = kwargs["tool_calls"][0]
                        if (is_assistant):
                            message = {
                                "role": "assistant",
                                "step_details": {
                                    "type": "tool_calls",
                                    "tool_calls": [
                                        {
                                            "id": tool_call["id"],
                                            "name": tool_call["function"]["name"],
                                            "args": tool_call["function"]["arguments"]
                                        }
                                    ] 
                                }
                            }
                        else:
                            message = {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": tool_call["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_call["function"]["name"],
                                            "arguments": tool_call["function"]["arguments"]
                                        }
                                    }
                                ]
                            }
                    elif (agent_result.response_metadata):
                        # Final update
                        message = {
                            "role": "assistant",
                            "content": agent_result.content
                        }
                        finish_reason = agent_result.response_metadata["finish_reason"]
                        if (finish_reason): 
                            message["content"] = ""
                        usage = {
                            "completion_tokens": agent_result.usage_metadata["output_tokens"],
                            "prompt_tokens": agent_result.usage_metadata["input_tokens"],
                            "total_tokens": agent_result.usage_metadata["total_tokens"]
                        }
                elif ("tools" in update):
                    tools = update["tools"]
                    tool_result = tools["messages"][0]
                    if (is_assistant):
                        message = {
                            "role": "assistant",
                            "step_details": {
                                "type": "tool_response",
                                "id": tool_result.id,
                                "tool_call_id": tool_result.tool_call_id,
                                "name": tool_result.name,
                                "content": tool_result.content
                            }
                        }
                    else:
                        message = {
                            "role": "tool",
                            "id": tool_result.id,
                            "tool_call_id": tool_result.tool_call_id,
                            "name": tool_result.name,
                            "content": tool_result.content
                        }
                else:
                    continue
            chunk_response = {
                "choices": [{
                    "index": 0,
                    "delta": message
                }]
            }
            if (finish_reason):
                chunk_response["choices"][0]["finish_reason"] = finish_reason
            if (usage):
                chunk_response["usage"] = usage
            yield chunk_response
    return generate, generate_stream