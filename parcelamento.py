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
    
      - Para transações de Débito:
          • Pagamento no próximo dia útil após a data da transação.
      
      - Para transações de Crédito:
          • Geração das parcelas originais: 
              - Para 1 parcela: vencimento 30 dias depois (ajustado para dia útil).
              - Para N parcelas: cada parcela vence a cada 30 dias (30, 60, 90, ...) a partir da data da transação,
                ajustando para o próximo dia útil.
    
    O valor ("value") está em centavos e é convertido para reais com duas casas decimais.
    
    O output inclui:
      - nsu, status, brand, gateway_name, merchant_issuer_specific_id
      - credit_or_debit (valor de product_name)
      - resolution_type
      - transaction_date (data da transação, no formato YYYY-MM-DD)
      - original_installments (lista de parcelas geradas)
    
    Se a transação for de crédito e tiver resolução "Automática", será criada também a chave "new_installment":
      - new_installment: única parcela com:
          • installment: 1
          • due_date: primeiro dia útil após a data da transação
          • amount: valor total da transação * (1 - taxa), onde a taxa é obtida de uma tabela fixa, de acordo com o número de parcelas.
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
        "transaction_date": payment_date.strftime("%Y-%m-%d"),
        "original_installments": original_installments
    }
    
    # Se a transação for de crédito com resolução "Automática", aplica a antecipação
    if product == "crédito" and transaction.get("resolution_type", "").lower() == "automática":
        parcels = transaction.get("parcels", 1)
        # Tabela de taxas fixas de 1 até 21 parcelas (taxa aplicada sobre o valor total)
        tax_table = {
            1: 0.02,
            2: 0.03,
            3: 0.04,
            4: 0.05,
            5: 0.06,
            6: 0.07,
            7: 0.08,
            8: 0.09,
            9: 0.10,
            10: 0.11,
            11: 0.12,
            12: 0.13,
            13: 0.14,
            14: 0.15,
            15: 0.16,
            16: 0.17,
            17: 0.18,
            18: 0.19,
            19: 0.20,
            20: 0.21,
            21: 0.22
        }
        if parcels not in tax_table:
            raise ValueError("Número de parcelas fora do limite suportado (1-21)")
        tax = tax_table[parcels]
        new_amount = (transaction["value"] * (1 - tax)) / 100  # valor líquido em reais
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
    
    # (Opcional) Defina uma lista de feriados se necessário
    holidays = []  # Exemplo: [datetime(2023, 12, 25).date()]
    
    # Processa cada transação e gera a nova tabela de recebíveis
    new_table = [create_receivables_schedule(t, holidays) for t in transactions]
    
    # Exibe o resultado formatado em JSON
    print(json.dumps(new_table, indent=2, ensure_ascii=False))
