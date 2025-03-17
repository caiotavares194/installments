import json
from datetime import datetime, timedelta

def parse_iso_date(date_str):
    """
    Converte uma string ISO para um objeto datetime.
    Se a string terminar com 'Z', substitui por '+00:00' para compatibilidade.
    """
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    return datetime.fromisoformat(date_str)

def next_business_day(date, holidays=None):
    """
    Retorna o próximo dia útil (segunda a sexta) que não seja feriado.
    'holidays' deve ser uma lista de objetos date.
    """
    if holidays is None:
        holidays = []
    while date.weekday() >= 5 or date.date() in holidays:
        date += timedelta(days=1)
    return date

def create_receivables_schedule(transaction, holidays=None):
    """
    Transforma uma transação em uma agenda de recebíveis conforme as regras:
    
      - Se o produto for "Débito": o pagamento é feito no próximo dia útil após a data de pagamento.
      - Se for "Crédito": 
          • Para 1 parcela: pagamento 30 dias depois (corrigindo para dia útil).
          • Para N parcelas: divide o valor igualmente (distribuindo o eventual resto) e
            cada parcela vence a cada 30 dias (30, 60, 90... dias, ajustando para o próximo dia útil).
      
    O campo "value" está em centavos e é convertido para reais com duas casas decimais.
    
    O output incluirá:
      - nsu, status, brand, gateway_name, merchant_issuer_specific_id
      - credit_or_debit (valor de product_name)
      - resolution_type
      - original_installments (lista de parcelas originais, cada uma com installment, due_date e amount)
      
    Se resolution_type for "Automática" e a transação for de crédito, será adicionada
    a chave new_installment, que representa a antecipação automática:
      - new_installment: única parcela com installment=1, due_date = primeiro dia útil após a transação,
        e amount = soma das parcelas originais multiplicada por (1 - taxa), onde:
           Taxa = 0.02 + (parcels - 1)*0.01
    """
    if holidays is None:
        holidays = []
    
    payment_date = parse_iso_date(transaction["payment_date"])
    product = transaction["product_name"].lower()
    original_installments = []
    
    if product == "débito":
        due_date = next_business_day(payment_date + timedelta(days=1), holidays)
        original_installments.append({
            "installment": 1,
            "due_date": due_date.strftime("%Y-%m-%d"),
            "amount": f"{transaction['value'] / 100:.2f}"
        })
    elif product == "crédito":
        parcels = transaction.get("parcels", 1)
        total_value = transaction["value"]
        installment_value = total_value // parcels
        remainder = total_value % parcels
        
        for i in range(1, parcels + 1):
            due_date = next_business_day(payment_date + timedelta(days=30 * i), holidays)
            extra = 1 if i <= remainder else 0
            installment_amount = installment_value + extra
            original_installments.append({
                "installment": i,
                "due_date": due_date.strftime("%Y-%m-%d"),
                "amount": f"{installment_amount / 100:.2f}"
            })
    else:
        raise ValueError("Produto não reconhecido. Use 'Débito' ou 'Crédito'.")
    
    result = {
        "nsu": transaction["nsu"],
        "status": transaction["status"],
        "brand": transaction["brand"],
        "gateway_name": transaction.get("gateway_name", ""),
        "merchant_issuer_specific_id": transaction.get("merchant_issuer_specific_id", ""),
        "credit_or_debit": transaction["product_name"],
        "resolution_type": transaction.get("resolution_type", ""),
        "original_installments": original_installments
    }
    
    # Se for crédito e a resolução for Automática, calcular o new_installment
    if product == "crédito" and transaction.get("resolution_type", "").lower() == "automática":
        parcels = transaction.get("parcels", 1)
        # Taxa: 2% para 1 parcela e aumenta 1% para cada parcela adicional
        tax = 0.02 + (parcels - 1) * 0.01
        # O valor total é a soma das parcelas (igual a transaction["value"])
        new_amount = (transaction["value"] * (1 - tax)) / 100  # Convertendo para reais
        new_due_date = next_business_day(payment_date + timedelta(days=1), holidays)
        result["new_installment"] = {
            "installment": 1,
            "due_date": new_due_date.strftime("%Y-%m-%d"),
            "amount": f"{new_amount:.2f}"
        }
    
    return result

if __name__ == "__main__":
    # Lê o JSON do arquivo base.json, que contém um array de transações
    with open('base.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Garante que data seja uma lista de transações
    transactions = data if isinstance(data, list) else [data]
    
    # (Opcional) Lista de feriados - ajuste conforme necessário
    holidays = []  # Exemplo: [datetime(2023, 12, 25).date()]
    
    # Processa cada transação e gera a nova tabela
    new_table = [create_receivables_schedule(t, holidays) for t in transactions]
    
    # Exibe o resultado formatado em JSON
    print(json.dumps(new_table, indent=2, ensure_ascii=False))
