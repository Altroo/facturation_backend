"""Shared, explicit text-only LoRA setup for training and capacity probes."""
import math
import re


def text_target_regex(total_layers, selected_layers):
    if not 1 <= selected_layers <= total_layers:
        raise ValueError('Invalid number of final LoRA text layers')
    indices = '|'.join(str(i) for i in range(total_layers-selected_layers, total_layers))
    return r'.*language_model\.layers\.('+indices+r')\.(mlp\.(up_proj|down_proj)|self_attn\.(q_proj|v_proj)|linear_attn\.(in_proj_qkv|out_proj))'


def configure_text_lora(model, *, layers, rank, alpha, checkpointing=False):
    if rank < 1 or not math.isfinite(alpha) or alpha <= 0:
        raise ValueError('LoRA rank and alpha must be positive and finite')
    from peft import LoraConfig, get_peft_model
    total_layers = model.config.text_config.num_hidden_layers
    regex = text_target_regex(total_layers, layers)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=rank, lora_alpha=alpha, lora_dropout=0.0,
        target_modules=regex, bias='none', task_type='CAUSAL_LM'))
    if checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    trainable = [name for name, value in model.named_parameters() if value.requires_grad]
    observed = {int(re.search(r'language_model\.layers\.(\d+)\.', name).group(1))
                for name in trainable if re.search(r'language_model\.layers\.(\d+)\.', name)}
    expected = set(range(total_layers-layers, total_layers))
    if observed != expected or any('lora_' not in name or 'language_model.layers.' not in name for name in trainable):
        raise ValueError('Unexpected trainable parameters; vision/base weights must remain frozen')
    return model, regex
