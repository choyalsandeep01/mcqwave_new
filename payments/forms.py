from django import forms
from .models import PaymentPlan

class PaymentForm(forms.Form):
    plan = forms.ModelChoiceField(
        queryset=PaymentPlan.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].widget.attrs.update({'class': 'form-select'})