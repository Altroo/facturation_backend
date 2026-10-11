from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from facture_client.models import FactureClient
from chat_ai_assistant.contracts import ChatAIError
from .tests import setup, executor
from .models import PendingAction

pytestmark = pytest.mark.django_db


def test_wrong_in_set_ordinal_cannot_create_proposal_even_on_current_page(setup):
    second = FactureClient.objects.create(client=setup.client,numero_facture='SYNTH-SECOND',
        date_facture=timezone.localdate(),created_by_user=setup.user,statut='Accepté')
    state={'resource':'invoice','ids':[setup.invoice.pk,second.pk],
           'expires_at':(timezone.now()+timedelta(minutes=5)).isoformat()}
    ex=executor(setup,state=state)
    ex.context={'invoice_id':setup.invoice.pk}
    ex.instruction='Delete the second invoice.'
    with patch('chat_ai.actions.target') as read_target:
        with pytest.raises(ChatAIError) as caught:
            ex.execute('prepare_change',{'resource':'invoice','identifier':setup.invoice.pk,'operation':'delete'})
        assert caught.value.code=='CONTEXT_EXPIRED'
        read_target.assert_not_called()
    assert not PendingAction.objects.exists()
    card=ex.execute('prepare_change',{'resource':'invoice','identifier':second.pk,'operation':'delete'})
    assert card['record_id']==second.pk
    assert FactureClient.objects.filter(pk=second.pk).exists()  # proposal only


def test_ordinal_matching_does_not_bypass_native_company_access(setup):
    ex=executor(setup,state={'resource':'invoice','ids':[setup.invoice.pk,setup.restricted.pk],
        'expires_at':(timezone.now()+timedelta(minutes=5)).isoformat()})
    ex.instruction='Supprime la deuxième facture.'
    with pytest.raises(ChatAIError) as caught:
        ex.execute('prepare_change',{'resource':'invoice','identifier':setup.restricted.pk,'operation':'delete'})
    assert caught.value.code=='NOT_FOUND'
    assert not PendingAction.objects.exists()

@pytest.mark.parametrize('resource,noun', [('credit_note',"facture d’avoir"),('proforma','facture pro forma')])
def test_complete_french_document_name_is_not_an_invoice(setup,resource,noun):
    ex=executor(setup,state={'resource':resource,'ids':[311,8092,1456],
        'expires_at':(timezone.now()+timedelta(minutes=5)).isoformat()})
    ex.instruction=f'Supprime la troisième {noun}.'
    # Exact ordinal reaches native target authorization. No fake business write.
    with patch('chat_ai.actions.target',side_effect=ChatAIError('NOT_FOUND')) as native:
        with pytest.raises(ChatAIError) as caught:
            ex.execute('prepare_change',{'resource':resource,'identifier':1456,'operation':'delete'})
        assert caught.value.code=='NOT_FOUND'
        native.assert_called_once()

@pytest.mark.parametrize("instruction", [
    "Delete client ID 743.",
    'Update client ID 743 notes to "invoice ID {identifier} is a reference".',
    "Update client ID 743 notes to invoice ID {identifier}.",
])
def test_explicit_other_target_rejects_before_native_record_read(setup,instruction):
    ex=executor(setup)
    ex.context={"invoice_id":setup.invoice.pk}
    ex.instruction=instruction.format(identifier=setup.invoice.pk)
    with patch("chat_ai.actions.target") as read_target:
        with pytest.raises(ChatAIError) as caught:
            ex.execute("prepare_change",{"resource":"invoice","identifier":setup.invoice.pk,"operation":"delete"})
        assert caught.value.code=="CONTEXT_EXPIRED"
        read_target.assert_not_called()
    assert not PendingAction.objects.exists()
