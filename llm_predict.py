"""
llm_predict.py — Inference engine using Qwen-2.5-14B-Instruct and QLoRA adapter to extract logits-based probabilities.
"""

import os
import torch
import math
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    HAS_LLM_PREDICT = True
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    BitsAndBytesConfig = None
    PeftModel = None
    HAS_LLM_PREDICT = False

# Global model and tokenizer cache to avoid reloading on every match
_MODEL_CACHE = None
_TOKENIZER_CACHE = None

def load_llm_model(model_id="Qwen/Qwen2.5-14B-Instruct", adapter_path="qwen_lora_adapter"):
    if not HAS_LLM_PREDICT:
        raise ImportError(
            "HuggingFace LLM libraries (transformers, peft, bitsandbytes) are not installed. "
            "Please install them using: pip install -r requirements.txt"
        )
    global _MODEL_CACHE, _TOKENIZER_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE, _TOKENIZER_CACHE

    print(f"[INFO] Loading tokenizer for {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    print(f"[INFO] Configuring 4-bit quantization for inference...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    print(f"[INFO] Loading base model {model_id}...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )

    # Check if QLoRA adapter exists
    if os.path.exists(adapter_path):
        print(f"[INFO] Loading LoRA adapter from {adapter_path}...")
        model = PeftModel.from_pretrained(model, adapter_path)
    else:
        print(f"[WARNING] LoRA adapter not found at '{adapter_path}'. Using base model for zero-shot prediction.")

    model.eval()
    _MODEL_CACHE = model
    _TOKENIZER_CACHE = tokenizer
    return model, tokenizer

def predict_match_probability(
    blue_name, red_name, blue_elo, red_elo, blue_obj, red_obj,
    blue_kills, red_kills, blue_dur, red_dur, blue_drag, red_drag,
    blue_towers, red_towers, blue_gold, red_gold,
    blue_picks=None, red_picks=None,
    model_id="Qwen/Qwen2.5-14B-Instruct", adapter_path="qwen_lora_adapter"
):
    model, tokenizer = load_llm_model(model_id, adapter_path)

    blue_picks_str = ", ".join(blue_picks) if blue_picks else "Not yet drafted"
    red_picks_str = ", ".join(red_picks) if red_picks else "Not yet drafted"

    prompt_text = (
        f"Match context:\n"
        f"Blue Team: {blue_name} (Elo: {blue_elo:.0f}, ObjCtrl: {blue_obj:.2f}, "
        f"AvgKills: {blue_kills:.1f}, AvgDuration: {blue_dur:.0f}s, "
        f"AvgDragons: {blue_drag:.1f}, AvgTowers: {blue_towers:.1f}, "
        f"AvgGold: {blue_gold:.0f})\n"
        f"Red Team: {red_name} (Elo: {red_elo:.0f}, ObjCtrl: {red_obj:.2f}, "
        f"AvgKills: {red_kills:.1f}, AvgDuration: {red_dur:.0f}s, "
        f"AvgDragons: {red_drag:.1f}, AvgTowers: {red_towers:.1f}, "
        f"AvgGold: {red_gold:.0f})\n\n"
        f"Draft picks:\n"
        f"Blue Team Picks: {blue_picks_str}\n"
        f"Red Team Picks: {red_picks_str}\n\n"
        f"Which team wins?"
    )

    messages = [
        {"role": "system", "content": "You are an expert League of Legends analyst. Predict the winner of the match based on ELO, historical stats, and the champion draft."},
        {"role": "user", "content": prompt_text}
    ]

    # Apply template and append prefix to force prediction
    chat_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    chat_prompt += "Winner: "

    # Tokenize input
    inputs = tokenizer(chat_prompt, return_tensors="pt").to(model.device)

    # Forward pass to extract logits of the next token
    with torch.no_grad():
        outputs = model(**inputs)
        next_token_logits = outputs.logits[0, -1, :]

    # Qwen tokenization for target classes "Blue" and "Red"
    blue_tids = [
        tokenizer.encode("Blue", add_special_tokens=False)[0],
        tokenizer.encode(" Blue", add_special_tokens=False)[0]
    ]
    red_tids = [
        tokenizer.encode("Red", add_special_tokens=False)[0],
        tokenizer.encode(" Red", add_special_tokens=False)[0]
    ]

    # Find the maximum logit for each class
    blue_logit = max(next_token_logits[tid].item() for tid in blue_tids)
    red_logit = max(next_token_logits[tid].item() for tid in red_tids)

    # Softmax probability calculation
    exp_blue = math.exp(blue_logit)
    exp_red = math.exp(red_logit)
    p_blue = exp_blue / (exp_blue + exp_red)

    return p_blue
