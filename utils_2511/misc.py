import numpy as np

def preprocess_function(examples, tokenizer, args):

    # Qwen2.5-Coder-32B
    # tokenizer.eos_token, tokenizer.bos_token, tokenizer.pad_token, tokenizer.unk_token
    # ('<|im_end|>', None, '<|PAD_TOKEN|>', None)
    # (151645, None, 151665, None)

    # Llama-3.1-8B
    # tokenizer.eos_token, tokenizer.bos_token, tokenizer.pad_token, tokenizer.unk_token
    # ('<|eot_id|>', '<|begin_of_text|>', '<|finetune_right_pad_id|>', None)
    # (128009, 128000, 128004, None)

    # how to use the function, becuase the tokenizer is not in the args

    # Add EOS token and truncate/pad
    if "llama" in args.model_name.lower() and args.use_eos_token:
        tokenized_inputs = tokenizer(
            [tokenizer.bos_token + text + tokenizer.eos_token for text in examples["text"]],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",  # Pad to max_length
            return_tensors="pt" #return pytorch tensors
    )
    elif "llama" in args.model_name.lower() and not args.use_eos_token:
        tokenized_inputs = tokenizer(
            [text for text in examples["text"]],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",  # Pad to max_length
            return_tensors="pt" #return pytorch tensors
        )
    elif "Qwen" in args.model_name.lower() and args.use_eos_token:
        tokenized_inputs = tokenizer(
            [text + tokenizer.eos_token for text in examples["text"]],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",  # Pad to max_length
            return_tensors="pt" #return pytorch tensors
        )
    elif "Qwen" in args.model_name.lower() and not args.use_eos_token:
        tokenized_inputs = tokenizer(
            [text for text in examples["text"]],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",  # Pad to max_length
            return_tensors="pt" #return pytorch tensors
        )
    else:
        raise ValueError(f"Model {args.model_name} not supported")
    return tokenized_inputs

def green(string: str) -> str:
    return f"\033[92m{string}\033[0m"

def red(string: str) -> str:
    return f"\033[91m{string}\033[0m"

def yellow(string: str) -> str:
    return f"\033[93m{string}\033[0m"

def is_landsat_modis_viirs_question(question, ref_dataset):

    result = ref_dataset[ref_dataset['Question'] == question]
    if len(result) > 0 and result.iloc[0]["Modality"] is not np.nan:
        result = result.iloc[0]["Modality"].lower()
    else:
        return False
    
    if "modis" in result or "landsat"   in result or "viirs" in result:
        print(green(f"Reference answer found: {result}"))
        return True
    else:
        print(yellow(f"Reference answer found: {result}"))
        return False