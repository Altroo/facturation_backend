"""Deterministic complete coverage, interleaved proportionally by application."""
import random

def complete_epoch_order(rows, seed=17, epoch=0):
    if not rows:raise ValueError('Empty training split')
    groups={}
    for index,row in enumerate(rows):
        app=row.get('application','facturation')
        groups.setdefault(app,[]).append(index)
    generator=random.Random(seed+epoch)
    positions=[]
    for app,indices in sorted(groups.items()):
        generator.shuffle(indices)
        positions.extend(((position+.5)/len(indices),app,index) for position,index in enumerate(indices))
    return [index for _,_,index in sorted(positions)]
