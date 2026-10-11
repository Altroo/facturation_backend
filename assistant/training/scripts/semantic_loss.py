"""Weight action names and argument content without masking tool syntax or EOS."""
import math
import re


def semantic_token_weights(rendered, prompt_characters, offsets, shared_tokens, weight):
    if not math.isfinite(weight) or weight<1:
        raise ValueError('Semantic weight must be finite and at least one')
    target=rendered[prompt_characters:]
    functions=list(re.finditer(r'<function=([^>\n]+)>',target))
    if len(functions)!=1:raise ValueError('Exactly one tool function span required')
    spans=[functions[0].span(1)]
    for parameter in re.finditer(r'<parameter=([^>\n]+)>\n(.*?)\n</parameter>',target,re.S):
        spans.extend([parameter.span(1),parameter.span(2)])
    spans=[(start+prompt_characters,end+prompt_characters) for start,end in spans]
    weights=[weight if any(start<right and end>left for left,right in spans) else 1.0
             for start,end in offsets[shared_tokens:]]
    if not weights or (weight>1 and not any(value>1 for value in weights)):
        raise ValueError('Missing weighted target tokens')
    return weights
