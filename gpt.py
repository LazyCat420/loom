import os
import time
import traceback
from pprint import pprint
import httpx
import json
import asyncio
import uuid

from celery import Celery
import openai
from util.util import retry, timestamp
from util.gpt_util import parse_logit_bias, parse_stop, get_correct_key
import requests
import codecs
import json

# response dictionary type
'''
{
    "completions": [{'text': string
                     'tokens': [token_data]
                     'finishReason': string}]
    "prompt": {
                'text': string,
                ? 'tokens': [token_data]
              }
    "id": string
    "model": string
    "timestamp": timestamp
}
'''

# token data dictionary type
'''
{
    'generatedToken': {'logprob': float,
                       'token': string}
    'position': {'end': int, 'start': int}
    ? 'counterfactuals': [{'token': float)}]
}
'''

# finishReason
'''
"finishReason": {"reason": "stop" | "length",
                 ? "sequence": string }
'''



#ai21_api_key = os.environ.get("AI21_API_KEY", None)

# Only initialize OpenAI client if we're using OpenAI models
if os.environ.get("OPENAI_API_KEY"):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
else:
    client = None


def gen(prompt, generation_settings, model_config, **kwargs):
    model = generation_settings["model"]
    model_info = model_config["models"][model]
    
    try:
        # Handle all models through generate() function
        response, error = generate(
            prompt=prompt,
            length=generation_settings['response_length'],
            num_continuations=generation_settings['num_continuations'],
            temperature=generation_settings['temperature'],
            logprobs=generation_settings['logprobs'],
            top_p=generation_settings['top_p'],
            model=generation_settings['model'],
            stop=parse_stop(generation_settings["stop"]) if generation_settings["stop"] else None,
            logit_bias=parse_logit_bias(generation_settings["logit_bias"]) if generation_settings["logit_bias"] else None,
            config=model_config,
            ai21_api_key=kwargs.get('AI21_API_KEY', os.environ.get("AI21_API_KEY", None))
        )
        return response, error

    except Exception as e:
        print(f"Generation error: {str(e)}")
        traceback.print_exc()
        return None, str(e)


def generate(config, **kwargs):
    model_type = config['models'][kwargs['model']]['type']
    
    # Add special handling for LMStudio
    if model_type == 'lmstudio':
        try:
            completions = []
            # Make separate calls for each continuation to get different responses
            for _ in range(kwargs['num_continuations']):
                response = httpx.post(
                    f"{config['models'][kwargs['model']]['api_base']}/chat/completions",
                    json={
                        "model": config['models'][kwargs['model']]['model'],
                        "messages": [
                            {"role": "system", "content": "You are a helpful AI assistant."},
                            {"role": "user", "content": kwargs['prompt']}
                        ],
                        "stream": False,
                        "temperature": kwargs['temperature'],
                        "max_tokens": -1
                    },
                    headers={
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    return None, f"LMStudio API error: {response.text}"
                
                result = response.json()
                completions.append({
                    "text": result["choices"][0]["message"]["content"],
                    "tokens": None,
                    "finishReason": result["choices"][0]["finish_reason"]
                })
            
            # Format response to match expected structure
            formatted_response = {
                "completions": completions,
                "prompt": {
                    "text": kwargs['prompt'],
                    "tokens": None
                },
                "id": str(uuid.uuid4()),
                "model": kwargs['model'],
                "timestamp": timestamp()
            }
            return formatted_response, None
            
        except Exception as e:
            print(f"LMStudio generation error: {str(e)}")
            traceback.print_exc()
            return None, str(e)
            
    # Add special handling for Ollama
    elif model_type == 'ollama':
        try:
            completions = []
            # Make separate calls for each continuation to get different responses
            for _ in range(kwargs['num_continuations']):
                response = httpx.post(
                    f"{config['models'][kwargs['model']]['api_base']}/api/generate",
                    json={
                        "model": config['models'][kwargs['model']]['model'],
                        "prompt": kwargs['prompt'],
                        "stream": False,
                        "temperature": kwargs['temperature'],
                        "top_p": kwargs['top_p'],
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    return None, f"Ollama API error: {response.text}"
                
                result = response.json()
                completions.append({
                    "text": result["response"],
                    "tokens": None,
                    "finishReason": "stop"
                })
            
            # Format response to match expected structure
            formatted_response = {
                "completions": completions,
                "prompt": {
                    "text": kwargs['prompt'],
                    "tokens": None
                },
                "id": str(uuid.uuid4()),
                "model": kwargs['model'],
                "timestamp": timestamp()
            }
            return formatted_response, None
            
        except Exception as e:
            print(f"Ollama generation error: {str(e)}")
            return None, str(e)
            
    elif model_type == 'ai21':
        response, error = ai21_generate(api_key=kwargs['ai21_api_key'], **kwargs)#config['AI21_API_KEY'], **kwargs)
        #save_response_json(response.json(), 'examples/AI21_response.json')
        if not error:
            formatted_response = format_ai21_response(response.json(), model=kwargs['model'])
            #save_response_json(formatted_response, 'examples/AI21_formatted_response.json')
            return formatted_response, error
        else:
            return response, error
    elif model_type in ('openai', 'openai-custom', 'gooseai', 'openai-chat', 'together', 'llama-cpp'):
        is_chat = model_type in ('openai-chat',)
        # for some reason, Together AI ignores the echo parameter
        echo = model_type not in ('together', 'openai-chat')
        # TODO: Together AI and chat inference breaks if logprobs is set to 0
        assert kwargs['logprobs'] > 0 or model_type not in ('together',), \
            "Logprobs must be greater than 0 for model type Together AI"
        # llama-cpp-python doesn't support batched inference yet: https://github.com/abetlen/llama-cpp-python/issues/771
        needs_multiple_calls = model_type in ('llama-cpp',)
        if needs_multiple_calls:
            required_calls = kwargs['num_continuations']
            kwargs['num_continuations'] = 1
            responses = []
            for _ in range(required_calls):
                response, error = openAI_generate(model_type, **kwargs)
                responses.append(response)
            response = responses[-1]
            response['choices'] = [r['choices'][0] for r in responses]
        else:
            # TODO OpenAI errors
            response, error = openAI_generate(model_type, **kwargs)
        #save_response_json(response, 'examples/openAI_response.json')
        formatted_response = format_openAI_response(response, kwargs['prompt'], echo=echo, is_chat=is_chat)
        #save_response_json(formatted_response, 'examples/openAI_formatted_response.json')
        return formatted_response, error


def completions_text(response):
    return [completion['text'] for completion in response['completions']]


def save_response_json(response, filename):
    with open(filename, 'w') as f:
        json.dump(response, f)

#################################
#   Janus
#################################

redis_url = os.environ.get("JANUS_REDIS", None)
app = Celery(
    # 'janus',
    broker=redis_url,
    backend=redis_url,
)

# get_gpt_response(prompt, memory, retry=True) -> result, error
janus_task = "janus.my_celery.tasks.get_gpt_response"


def janus_generate(prompt, memory=""):
    assert isinstance(prompt, str) and isinstance(memory, str)
    celery_task = app.send_task(janus_task, args=[prompt, memory])
    print("Sent to janus")
    result, error = celery_task.get()
    return result, error


#################################
#   OpenAI
#################################

#openai.api_key = os.environ.get("OPENAI_API_KEY", None)


def fix_openAI_token(token):
    # if token is a byte string, convert to string
    # TODO this doesn't work
    decoded = codecs.decode(token, "unicode-escape")
    return decoded
    # byte_token = decoded.encode('raw_unicode_escape')
    # return byte_token.decode('utf-8')


def format_openAI_token_dict(completion, token, i, offset):
    calculated_offset = len(token) + offset
    token_dict = {'generatedToken': {'token': token,
                                     'logprob': completion['logprobs']['token_logprobs'][i]},
                  'position': calculated_offset}
    if completion['logprobs'].get('top_logprobs', None) is not None and \
        completion['logprobs']['top_logprobs']:
        openai_counterfactuals = completion['logprobs']['top_logprobs'][i]
        if openai_counterfactuals:
            sorted_counterfactuals = {k: v for k, v in
                                    sorted(openai_counterfactuals.items(), key=lambda item: item[1], reverse=True)}
            token_dict['counterfactuals'] = sorted_counterfactuals
    else:
        token_dict['counterfactuals'] = None
    return token_dict, calculated_offset

def format_openAI_chat_token_dict(content_token, i):
    token_dict = {
        'generatedToken': {'token': content_token['token'],
                           'logprob': content_token['logprob']},
                           'position': i,
                           'counterfactuals' : {c['token']: c['logprob'] for c in content_token['top_logprobs']}
        }
    return token_dict

def format_openAI_completion(completion, prompt_offset, prompt_end_index, is_chat):
    if 'text' in completion:
        completion_text = completion['text']
    else:
        completion_text = completion['message']['content']
    completion_dict = {'text': completion_text[prompt_offset:],
                       'finishReason': completion['finish_reason'],
                       'tokens': []}
    offset = prompt_offset
    if is_chat:
        for i, token in enumerate(completion['logprobs']['content']):
            token_dict = format_openAI_chat_token_dict(token, i)
            completion_dict['tokens'].append(token_dict)
    else:
        for i, token in enumerate(completion['logprobs']['tokens'][prompt_end_index:]):
            j = i + prompt_end_index
            token_dict, offset = format_openAI_token_dict(completion, token, j, offset)
            completion_dict['tokens'].append(token_dict)
    return completion_dict


def format_openAI_prompt(completion, prompt, prompt_end_index):
    prompt_dict = {'text': prompt, 'tokens': []}
    # loop over tokens until offset >= prompt length
    offset = 0
    for i, token in enumerate(completion['logprobs']['tokens'][:prompt_end_index]):
        token_dict, offset = format_openAI_token_dict(completion, token, i, offset)
        prompt_dict['tokens'].append(token_dict)

    return prompt_dict


def format_openAI_response(response, prompt, echo, is_chat):
    if echo:
        prompt_end_index = response['usage']['prompt_tokens']
        prompt_dict = format_openAI_prompt(response['choices'][0],
                                                             prompt,
                                                             prompt_end_index)
    else:
        prompt_dict = {'text': prompt, 'tokens': None}
        prompt_end_index = 0
        #prompt = ''

    prompt_offset = len(prompt) if echo else 0

    response_dict = {'completions': [format_openAI_completion(completion, prompt_offset, prompt_end_index, is_chat) for
                                     completion in response['choices']],
                     'prompt': prompt_dict,
                     'id': response['id'],
                     'model': response['model'],
                     'timestamp': timestamp()}
    return response_dict


@retry(n_tries=3, delay=1, backoff=2, on_failure=lambda *args, **kwargs: ("", None))
def openAI_generate(model_type, prompt, length=150, num_continuations=1, logprobs=10, temperature=0.8, top_p=1, stop=None,
                    model='davinci', logit_bias=None, **kwargs):
    # Return early if we don't have an OpenAI client and we're trying to use OpenAI
    if not client and model_type in ('openai', 'openai-custom', 'openai-chat'):
        return None, "OpenAI API key not configured"
        
    if not logit_bias:
        logit_bias = {}
    params = {
        'temperature': temperature,
        'max_tokens': length,
        'top_p': top_p,
        'logprobs': logprobs,
        'logit_bias': logit_bias,
        'n': num_continuations,
        'stop': stop,
        'model': model,
    }
    if model_type == 'openai-chat':
        params['messages'] = [{ 'role': "assistant", 'content': prompt }]
        params['logprobs'] = True
        params['top_logprobs'] = logprobs
        response = client.chat.completions.create(
            **params
        ).to_dict()
    else:
        params['prompt'] = prompt
        params['echo'] = True
        response = client.completions.create(
            **params
        ).to_dict()

    return response, None


def search(query, documents, engine="curie"):
    return client.Engine(engine).search(
        documents=documents,
        query=query
    )


#################################
#   AI21
#################################


def fix_ai21_tokens(token):
    return token.replace("▁", " ").replace("<|newline|>", "\n")

def ai21_token_position(textRange, text_offset):
    return {'start': textRange['start'] + text_offset,
            'end': textRange['end'] + text_offset}

def format_ai21_token_data(token, prompt_offset=0):
    token_dict = {'generatedToken': {'token': fix_ai21_tokens(token['generatedToken']['token']),
                                     'logprob': token['generatedToken']['logprob']},
                  'position': ai21_token_position(token['textRange'], prompt_offset)}
    if token['topTokens']:
        token_dict['counterfactuals'] = {fix_ai21_tokens(c['token']): c['logprob'] for c in token['topTokens']}
    else:
        token_dict['counterfactuals'] = None
    return token_dict


def format_ai21_completion(completion, prompt_offset=0):
    completion_dict = {'text': completion['data']['text'],
                       'tokens': [format_ai21_token_data(token, prompt_offset) for token in completion['data']['tokens']],
                       'finishReason': completion['finishReason']['reason']}
    return completion_dict


def format_ai21_response(response, model):
    prompt = response['prompt']['text']
    response_dict = {'completions': [format_ai21_completion(completion, prompt_offset=len(prompt)) for completion in response['completions']],
                     'prompt': {'text': prompt,
                                'tokens': [format_ai21_token_data(token, prompt_offset=0) for token in response['prompt']['tokens']]},
                     'id': response['id'],
                     'model': model,
                     'timestamp': timestamp()}
    return response_dict


def ai21_generate(prompt, length=150, num_continuations=1, logprobs=10, temperature=0.8, top_p=1, stop=None,
                  engine='j1-large', api_key=None, **kwargs):
    stop = stop if stop else []
    request_json = {
        "prompt": prompt,
        "numResults": num_continuations,
        "maxTokens": length,
        "stopSequences": stop,
        "topKReturn": logprobs,
        "temperature": temperature,
        "topP": top_p,
    }
    try:
        response = requests.post(
            f"https://api.ai21.com/studio/v1/{engine}/complete",
            headers={"Authorization": f"Bearer {api_key}"},
            json=request_json,
        )
    except requests.exceptions.ConnectionError:
        return None, 'Connection error'
    error = None
    if response.status_code != 200:
        error = f'Bad status code {response.status_code}'
        print(request_json)
    return response, error


if __name__ == "__main__":
    pass
