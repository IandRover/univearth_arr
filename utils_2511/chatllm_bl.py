import os, re, anthropic
from typing import List, Dict, Optional
from openai import OpenAI
import json
from google import genai
from google.genai import types
# from together import Together

class ChatLLM:
    def __init__(self, args, llm) -> None:

        self.strategy = args.strategy
        self.cur_iter = 0
        self.text_generator = llm
        self.language = args.language

        # self.model_name = args.model_name
        self.valid_model_list = [
            "haiku", "sonnet", "claude-3.7",
            "gpt-4o", "gpt-4o-mini", "o3-mini", "o5-mini",
            # "qwen-2.5-coder-32b-instruct",
            "Llama-3.1-8B-Instruct",
            "Qwen2.5-Coder-32B-Instruct",
            "Llama-3.3-70B-Instruct", 
            "Llama-3.2-3B-Instruct",
            "Llama-3.2-1B-Instruct",
            "Qwen-2.5-72B-Instruct",
            "DeepSeek-V3", # huggingface
            # "Qwen-2.5-Coder-32B-Instruct", 
            "Qwen2.5-Coder-32B-Instruct",
            "deepseek-chat-v3",
            "deepseek-reasoner",
            "codellama/CodeLlama-13b-hf",
            "DeepSeek-R1-Distill-Qwen-32B",
            # Gemini
            "gemini", 'gemini-2.5-pro', "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash",
            "gemini-3-pro-preview",
            # OpenRouter
            ]
        
        self.prompt_system_zs = open("./prompts_2511/2323_ZS_SYSTEM.txt").read()
        self.prompt_system_zs_js = open("./prompts_2511/2323_ZS_SYSTEM_JS.txt").read()
        self.prompt_user_zs = open("./prompts_2511/2323_ZS_USER.txt").read()

        self.prompt_system_answer = open("./prompts_2511/2323_ANS_SYSTEM.txt").read()
        self.prompt_user_answer = open("./prompts_2511/2323_ANS_USER.txt").read()

        self.temp_code_system_prompt = None
        self.temp_code_user_prompts = []
        self.should_clean_utf8 = False
        
    def _make_api_call(self, system_prompt, user_prompts) -> str:

        if self.request_type == "openai":
            messages = [{ "role": "system", "content": system_prompt}]
            messages.append({ "role": "user", "content": user_prompts[-1]})            
            self.temp_messages = messages 

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                # max_completion_tokens=4096,
            )
            return response.choices[0].message.content

        elif self.request_type == "huggingface":

            messages = [{ "role": "system", "content": system_prompt}]
            messages.append({ "role": "user", "content": user_prompts[-1]})

            self.temp_messages = messages 

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                # user="chkao",
            )
            return response.choices[0].message.content
        
        elif self.request_type == "anthropic":

            messages = []
            messages.append({ "role": "user", "content": user_prompts[-1]})

            response = self.client.messages.create(
                system= [{"type": "text",
                          "text": system_prompt,
                          "cache_control": {"type": "ephemeral"}}],
                model=self.model,
                messages=messages,
                max_tokens=4096,
            )
            return response.content[0].text

        elif self.request_type == "gemini":

            messages = [{ "role": "system", "content": system_prompt}]
            messages.append({ "role": "user", "content": user_prompts[-1]})
            
            self.temp_messages = messages 

            if self.model.startswith("gemini-2.5"):
                thinking_config = types.ThinkingConfig(thinking_budget=1024)

            elif self.model.startswith("gemini-3"):
                thinking_config=types.ThinkingConfig(thinking_level="low")

            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        thinking_config=thinking_config
                        ),
                contents=user_prompts[-1],
                # max_completion_tokens=4096,
            )
            return response.text 

        elif self.request_type == "openrouter":

            messages = [{ "role": "system", "content": system_prompt}]
            messages.append({ "role": "user", "content": user_prompts[-1]})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                )
            
            return response.choices[0].message.content

        elif self.request_type == "together":

            messages = [{ "role": "system", "content": system_prompt}]
            messages.append({ "role": "user", "content": user_prompts[-1]})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                )
            
            return response.choices[0].message.content
        
    def _check_option(self, content: str, options: List[str]) -> bool:
        # if only one option is in content and other options are not in content, return the option
        # if multiple options are in content, return None
        found_options = []
        for option in options:
            if option in content:
                found_options.append(option)
        if len(found_options) == 1:
            return found_options[0]
        else:
            return None

    def _parse(self, content: str, patterns: List[str]) -> Dict[str, Optional[str]]:
        result = {}
        for pattern in patterns:
            if pattern in ["code", "Code", "CODE"]:
                code_patterns = [
                                # python 
                                r"<code>```python\s*(.*?)\s*```</code>",
                                r"<Code>```python\s*(.*?)\s*```</Code>",
                                r"```python\s*(.*?)\s*```",
                                # javascript
                                r"<code>```javascript\s*(.*?)\s*```</code>",
                                r"<Code>```javascript\s*(.*?)\s*```</Code>",
                                r"```javascript\s*(.*?)\s*```",
                                r"<code>```Javascript\s*(.*?)\s*```</code>",
                                r"<Code>```Javascript\s*(.*?)\s*```</Code>",
                                r"```Javascript\s*(.*?)\s*```",   
                                # general     
                                r"<code>```\s*(.*?)\s*```</code>",
                                r"<Code>```\s*(.*?)\s*```</Code>",
                                r"```\s*(.*?)\s*```",
                                r"<code>(.*?)</code>",
                                r"<Code>(.*?)</Code>",
                            ]

                candidate_code = None
                for code_pattern in code_patterns:
                    match = re.search(code_pattern, content, re.DOTALL)
                    if match:
                        if candidate_code is None:
                            candidate_code = match.group(1).strip()
                        else:
                            cur_candidate_code = match.group(1).strip()
                            if cur_candidate_code.startswith("import") and not cur_candidate_code.endswith("```"):
                                if len(cur_candidate_code) > len(candidate_code):
                                    candidate_code = cur_candidate_code
                                
                result[pattern] = candidate_code

                if pattern not in result:
                    result[pattern] = None
            else:
                template = f"<{pattern}>(.*?)</{pattern}>"
                match = re.search(template, content, re.DOTALL)
                result[pattern] = match.group(1).strip() if match else None

                if pattern == "answer" and "<answer>" in content and "</answer>" not in content:
                    result[pattern] =  content.split("<answer>")[1]
                elif pattern == "answer" and "<answer>" not in content:
                    result[pattern] = self._check_option(content, ["A", "B", "C1", "C2", "C3", "D"])

        return result
    
    def reset(self):
        self.cur_iter = 1

    def generate_code(self, info: dict):

        if self.language == "javascript" and self.strategy == "zero_shot":
            self.temp_code_system_prompt = self.prompt_system_zs_js
            self.temp_code_user_prompts = [self.prompt_user_zs.format_map(info)] 
        elif self.language == "python" and self.strategy == "zero_shot":
            self.temp_code_system_prompt = self.prompt_system_zs
            self.temp_code_user_prompts = [self.prompt_user_zs.format_map(info)]
        else:
            raise ValueError(f"Invalid strategy or language: {self.strategy} + {self.language}")
        
        self._get_client(self.text_generator)
        self.temp_response = ""
        self.temp_code = ""
        try:
            self.temp_response = self._make_api_call(self.temp_code_system_prompt, self.temp_code_user_prompts)
            self.temp_code = self._parse(self.temp_response, ["code"])["code"]
            if not self.temp_code:
                assert False, "No <code> is found in the response."
        except Exception as e:
            if "The model is overloaded. Please try again later." in str(e):
                return {}
            
            print(f"error: {e}")
            self.temp_code = f"""'No <code> is found in the response. Please try again. The exception error is: {e}'"""
        return {"raw_code": self.temp_response, "code": self.temp_code}
    
    def generate_answer(self, info: dict):

        self.temp_ans_system_prompt = self.prompt_system_answer
        self.temp_ans_user_prompt = self.prompt_user_answer.format_map(info)

        self._get_client(self.text_generator)
        self.temp_raw_answer = self._make_api_call(self.temp_ans_system_prompt, [self.temp_ans_user_prompt])
        self.temp_answer = self._parse(self.temp_raw_answer, ["answer"])["answer"]
        self.temp_thinking = self._parse(self.temp_raw_answer, ["thinking"])["thinking"]
        if not self.temp_answer:
            raise ValueError("Failed to generate valid answer")
        return {"raw_answer": self.temp_raw_answer, "answer": self.temp_answer, "answer_thinking": self.temp_thinking}
    
    def _get_client(self, model_name: str):

        # check if model_name is valid
        assert model_name in self.valid_model_list, f"Invalid model name: {model_name}"
        
        # huggingface
        if model_name == "Qwen2.5-Coder-32B-Instruct":
            model = "Qwen/Qwen2.5-Coder-32B-Instruct"
            request_type = "huggingface"
        elif model_name == "Llama-3.3-70B-Instruct":
            model = "meta-llama/Llama-3.3-70B-Instruct"
            request_type = "huggingface"
        elif model_name == "Llama-3.2-3B-Instruct":
            model = "meta-llama/Llama-3.2-3B-Instruct"
            request_type = "huggingface"
        elif model_name == "Llama-3.2-1B-Instruct":
            model = "meta-llama/Llama-3.2-1B-Instruct"
            request_type = "huggingface"
        elif model_name == "Qwen-2.5-72B-Instruct":
            model = "Qwen/Qwen2.5-72B-Instruct"
            request_type = "huggingface"
        elif model_name == "codellama/CodeLlama-13b-hf":
            model = "codellama/CodeLlama-13b-hf"
            request_type = "huggingface"
        elif model_name == "DeepSeek-R1-Distill-Qwen-32B":
            model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
            request_type = "huggingface"
        elif model_name == "DeepSeek-V3":
            model = "deepseek-ai/DeepSeek-V3"
            request_type = "huggingface"
        elif model_name == "Llama-3.1-8B-Instruct":
            model = "meta-llama/Llama-3.1-8B-Instruct"
            request_type = "huggingface"
            

        # deepseek
        elif model_name == "deepseek-chat-v3":
            model = "deepseek-chat"
            request_type = "openai-deepseek"
        elif model_name == "deepseek-reasoner":
            model = "deepseek-reasoner"
            request_type = "openai-deepseek"

        # openai
        elif model_name == "gpt-4o-mini":
            model = "gpt-4o-mini"
            request_type = "openai"
        elif model_name == "gpt-4o":
            model = "gpt-4o"
            request_type = "openai"
        elif model_name == "o3-mini":
            model = "o3-mini"
            request_type = "openai"
        elif model_name == "o5-mini":
            model = "gpt-5-mini"
            request_type = 'openai'
            self.should_clean_utf8 = True

        # anthropic
        elif model_name == "haiku":
            model = "claude-3-5-haiku-20241022"
            request_type = "anthropic"
        elif model_name == "sonnet":
            model = "claude-3-5-sonnet-20241022"
            request_type = "anthropic"
        elif model_name == "claude-3.7":
            model = "claude-3-7-sonnet-20250219"
            request_type = "anthropic"

        # gemini
        elif model_name == "gemini-2.0-flash":
            model = "gemini-2.0-flash"
            request_type = "gemini"
        elif model_name == "gemini-2.5-pro":
            model = "gemini-2.5-pro"
            request_type = 'gemini'
        elif model_name == "gemini-2.5-flash":
            model = "gemini-2.5-flash"
            request_type = 'gemini'
        elif model_name == "gemini-2.5-flash-lite":
            model = "gemini-2.5-flash-lite"
            request_type = 'gemini'
        elif model_name == "gemini-3-pro-preview":
            model = "gemini-3-pro-preview"
            request_type = 'gemini'
        
        # openrouter
        elif model_name == "OR-Llama-3.3-70B-Instruct":
            model = "meta-llama/llama-3.3-70b-instruct:free"
            request_type = "openrouter"
        elif model_name == "OR-phi-3-medium":
            model = "microsoft/phi-3-medium-128k-instruct:free"
            request_type = "openrouter"
        elif model_name == "OR-deepseek-r1-distill-llama-70b":
            model = "deepseek/deepseek-r1-distill-llama-70b:free"
            request_type = "openrouter"

        # together AI
        elif model_name == "tgt-Llama-3.3-70B-Instruct":
            model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
            request_type = "together"
        elif model_name == "tgt-Llama-3.3-70B-Instruct-Turbo-Free":
            model = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"
            request_type = "together"
        elif model_name == "tft-DeepSeek-V3":
            model = "deepseek-ai/DeepSeek-V3"
            request_type = "together"
        elif model_name == "tft-DeepSeek-R1":
            model = "deepseek-ai/DeepSeek-R1"
            request_type = "together"
        elif model_name == "tft-DeepSeek-R1-Distill-Llama-70B-free":
            model = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"
            request_type = "together"
        elif model_name == "tft-DeepSeek-R1-Distill-Llama-70B":
            model = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B"
            request_type = "together"
        elif model_name == "tft-Qwen2.5-Coder-32B-Instruct":
            model = "Qwen/Qwen2.5-Coder-32B-Instruct"
            request_type = "together"
        elif model_name == "tft-Qwen2.5-72B-Instruct-Turbo":
            model = "Qwen/Qwen2.5-72B-Instruct-Turbo"
            request_type = "together"

            
        if request_type == "anthropic":
            self.client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        elif request_type == "openai":
            self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        elif request_type == "huggingface":
            # self.client = OpenAI(base_url="https://api-inference.huggingface.co/v1/", 
            #                      api_key=os.environ["HUGGINGFACE_API_KEY"])
            # self.top_p = 0.99
            from huggingface_hub import InferenceClient
            self.client = InferenceClient(
                provider="hf-inference",
                api_key=os.environ.get('HUGGINGFACE_API_KEY'),
            )
        elif request_type == "openai-deepseek":
            self.client = OpenAI(api_key="sk-0c2900b9c0ca4a44a4ad79bc09eefba3", 
                                base_url="https://api.deepseek.com")

        elif request_type == "gemini":
            self.client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            # self.chat = self.client.chats.create(model="gemini-2.0-flash")

        # elif request_type == "openrouter":
        #     self.client = OpenAI(
        #                         base_url="https://openrouter.ai/api/v1",
        #                         api_key=os.environ["OPENROUTER_API_KEY"],
        #                         )
        
        # elif request_type == "together":
        #     self.client = Together()

        else:
            raise ValueError(f"Invalid request type: {request_type}")
            

        self.model = model
        self.request_type = request_type

    def _set_top_p(self, top_p=1):
        self.top_p = max(min(top_p, 0.99), 0.01)