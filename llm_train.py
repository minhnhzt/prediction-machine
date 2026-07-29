"""
llm_train.py — Train Qwen-2.5-14B-Instruct using QLoRA in 4-bit precision on H100 GPU.
"""

import os
import torch
try:
    from datasets import load_dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments
    )
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer
    HAS_LLM_TRAIN = True
except (ImportError, OSError):
    load_dataset = None
    AutoModelForCausalLM = None
    AutoTokenizer = None
    BitsAndBytesConfig = None
    TrainingArguments = None
    LoraConfig = None
    get_peft_model = None
    TaskType = None
    SFTTrainer = None
    HAS_LLM_TRAIN = False

def train_llm(model_id="Qwen/Qwen2.5-14B-Instruct", train_path="llm_train.jsonl", val_path="llm_val.jsonl", output_dir="qwen_lora_adapter"):
    if not HAS_LLM_TRAIN:
        raise ImportError(
            "HuggingFace LLM libraries (transformers, peft, trl, bitsandbytes, datasets) are not installed. "
            "Please install them using: pip install -r requirements.txt"
        )
    print(f"[INFO] Loading datasets from {train_path} and {val_path}...")
    dataset = load_dataset("json", data_files={"train": train_path, "validation": val_path})

    print(f"[INFO] Initializing tokenizer for {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Setup 4-bit quantization config (BitsAndBytes)
    print(f"[INFO] Configuring 4-bit quantization...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    print(f"[INFO] Loading base model {model_id} in 4-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )
    model.config.use_cache = False  # Disable for training to save memory

    # Setup PEFT LoRA Config
    print(f"[INFO] Configuring LoRA adapters...")
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM
    )

    # Format messages to Qwen chat template
    def format_chat_template(example):
        texts = []
        for messages in example["messages"]:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            texts.append(text)
        return {"text": texts}

    print(f"[INFO] Formatting dataset with Qwen chat template...")
    formatted_dataset = dataset.map(format_chat_template, batched=True, remove_columns=["messages"])

    # Setup SFT Trainer
    print(f"[INFO] Preparing Training Arguments...")
    training_args = TrainingArguments(
        output_dir="qwen_lora_temp_output",
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=10,
        num_train_epochs=3,
        bf16=True,  # H100 supports bfloat16 natively
        save_strategy="no",
        evaluation_strategy="epoch",
        report_to="none",
        optim="paged_adamw_8bit"  # Save VRAM during training
    )

    print(f"[INFO] Starting SFTTrainer execution...")
    trainer = SFTTrainer(
        model=model,
        train_dataset=formatted_dataset["train"],
        eval_dataset=formatted_dataset["validation"],
        peft_config=peft_config,
        dataset_text_field="text",
        max_seq_length=512,
        tokenizer=tokenizer,
        args=training_args
    )

    trainer.train()

    print(f"[INFO] Saving the trained LoRA adapter to {output_dir}...")
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    print(f"[SUCCESS] QLoRA Fine-tuning complete. Adapter saved to {output_dir}.")

if __name__ == "__main__":
    train_llm()
