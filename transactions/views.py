from django.contrib import messages
from django.shortcuts import render , get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.views import View
from django.http import HttpResponse
from django.views.generic import CreateView, ListView
from transactions.constants import DEPOSIT, WITHDRAWAL, LOAN, LOAN_PAID
from datetime import datetime
from django.db.models import Sum
from accounts.models import UserBankAccount
from transactions.forms import (
    DepositForm,
    WithdrawForm,
    LoanRequestForm,
    TransferForm
)
from transactions.models import Transaction


def transfer_view(request):
    if request.method == 'POST':
        account_no = int(request.POST.get('acc'))
        
        amount = int(request.POST.get('amount'))
        sender_acc = request.user.account
        # check= get_object_or_404(UserBankAccount,account_no = account_no)
        # check = UserBankAccount.objects.get(account_no = account_no)
        check = UserBankAccount.objects.filter(account_no = account_no).first()
        if check:
            reciver_acc = UserBankAccount.objects.get(account_no = account_no)
            if sender_acc.balance > amount:
                sender_acc.balance -= amount
                reciver_acc.balance += amount
                sender_acc.save(update_fields=['balance'])
                reciver_acc.save(update_fields=['balance'])
                email_subject = "Money Transfer"
                email_body_sender = render_to_string("transactions/transfer_email_send.html",{'account_s':sender_acc,'account_r':reciver_acc,'amount':amount})
                email_body_reciver = render_to_string("transactions/transfer_email_receive.html",{'account_r':reciver_acc,'account_s':sender_acc,'amount':amount})
                email_s = EmailMultiAlternatives(email_subject,'',to=[sender_acc.user.email])
                email_r = EmailMultiAlternatives(email_subject,'',to=[reciver_acc.user.email])
                email_s.attach_alternative(email_body_sender,'text/html')
                email_r.attach_alternative(email_body_reciver,'text/html')
                email_s.send()
                email_r.send()
                
                
                messages.success(request,f'{amount}$ is transfere to {reciver_acc.user.username} succesfully')
            else:
                messages.success(request,f'You don not have sufficient ammount.')
        else:
            messages.warning(request,f'No account found with this {account_no} account number.')
    return render(request,'transactions/transaction_form.html',{'title':'Transfer'})

class TransferView(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    success_url = reverse_lazy('transaction_report')
    title = 'Transfer'
    form_class = TransferForm

    def get_initial(self):
        initial = {'transaction_type': 'Transfer'}
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)  # template e context data pass kora
        context.update({
            'title': self.title
        })

        return context

    def form_valid(self, form):
        amount = form.cleaned_data['amount']
        acc_no = form.cleaned_data['account_no']
        account = self.request.user.account
        to_acc = UserBankAccount.objects.get(account_no=acc_no)
        account.balance -= amount
        to_acc += amount
        account.save(
            update_fields=[
                'balance'
            ]
        )
        to_acc.save(
            update_fields=[
                'balance'
            ]
        )


class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'account': self.request.user.account
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)  # template e context data pass kora
        context.update({
            'title': self.title
        })

        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        account.balance += amount
        account.save(
            update_fields=[
                'balance'
            ]
        )

        messages.success(
            self.request,
            f'{"{:,.2f}".format(float(amount))
               }$ was deposited to your account successfully'
        )

        return super().form_valid(form)


class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money'
    success_url = reverse_lazy('deposit_money')
    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):

        if self.request.user.account.bankrupt:
            messages.warning(
                self.request,
                f'Bankrupt. You can Not withdraw money.'
            )
        else:
            amount = form.cleaned_data.get('amount')
            self.request.user.account.balance -= form.cleaned_data.get('amount')
            self.request.user.account.save(update_fields=['balance'])

            messages.success(
                self.request,
                f'Successfully withdrawn {"{:,.2f}".format(
                    float(amount))}$ from your account'
            )

        return super().form_valid(form)


class LoanRequestView(TransactionCreateMixin):
    form_class = LoanRequestForm
    title = 'Request For Loan'

    def get_initial(self):
        initial = {'transaction_type': LOAN}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        current_loan_count = Transaction.objects.filter(
            account=self.request.user.account, transaction_type=3, loan_approve=True).count()
        if current_loan_count >= 3:
            return HttpResponse("You have cross the loan limits")
        messages.success(
            self.request,
            f'Loan request for {"{:,.2f}".format(
                float(amount))}$ submitted successfully'
        )

        return super().form_valid(form)


class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    balance = 0  # filter korar pore ba age amar total balance ke show korbe

    def get_queryset(self):
        queryset = super().get_queryset().filter(
            account=self.request.user.account
        )
        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            queryset = queryset.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date)
            self.balance = Transaction.objects.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date
            ).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance

        return queryset.distinct()  # unique queryset hote hobe

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'account': self.request.user.account
        })

        return context


class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(Transaction, id=loan_id)
        print(loan)
        if loan.loan_approve:
            user_account = loan.account
            # Reduce the loan amount from the user's balance
            # 5000, 500 + 5000 = 5500
            # balance = 3000, loan = 5000
            if loan.amount < user_account.balance:
                user_account.balance -= loan.amount
                loan.balance_after_transaction = user_account.balance
                user_account.save()
                loan.loan_approved = True
                loan.transaction_type = LOAN_PAID
                loan.save()
                return redirect('transactions:loan_list')
            else:
                messages.error(
                    self.request,
                    f'Loan amount is greater than available balance'
                )

        return redirect('loan_list')


class LoanListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'transactions/loan_request.html'
    context_object_name = 'loans'  # loan list ta ei loans context er moddhe thakbe

    def get_queryset(self):
        user_account = self.request.user.account
        queryset = Transaction.objects.filter(
            account=user_account, transaction_type=3)
        print(queryset)
        return queryset
