from flask import Flask, render_template, jsonify, request
import requests
import sqlite3
import os
from groq import Groq
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)
DATABASE = 'banco_investimentos.db'

# --- CONFIGURAÇÃO DO GROQ SEGURA ---
# O Python agora puxa a chave direto do sistema, sem expô-la no código!
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def iniciar_banco():
    """Cria a tabela no banco de dados se ela ainda não existir"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carteira (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            qtd INTEGER NOT NULL,
            preco REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

iniciar_banco()

def buscar_dados_economia():
    """Busca as cotações macroeconômicas de mercado"""
    dados = {
        "ibovespa": {"valor": "125.000", "variacao": 0.0},
        "dolar": {"valor": "5.40", "variacao": 0.0},
        "selic": "10,50% a.a.",
        "ipca": "4,25%"
    }
    try:
        url_hg = "https://api.hgbrasil.com/finance?format=json"
        resposta_hg = requests.get(url_hg, timeout=5).json()
        
        ibov_data = resposta_hg['results']['stocks']['IBOVESPA']
        dados['ibovespa']['valor'] = f"{ibov_data['points']:,}".replace(',', '.')
        dados['ibovespa']['variacao'] = ibov_data['variation']
        
        dolar_data = resposta_hg['results']['currencies']['USD']
        dados['dolar']['valor'] = f"{dolar_data['buy']:.2f}".replace('.', ',')
        dados['dolar']['variacao'] = dolar_data['variation']
    except Exception as e:
        print(f"Erro ao carregar APIs externas: {e}")
    return dados

@app.route('/')
def dashboard():
    informacoes_mercado = buscar_dados_economia()
    return render_template('index.html', mercado=informacoes_mercado)

# ----------------- ROTAS DA CARTEIRA -----------------

@app.route('/api/carteira', methods=['GET'])
def listar_ativos():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, tipo, qtd, preco FROM carteira")
    linhas = cursor.fetchall()
    conn.close()
    
    ativos = []
    for linha in linhas:
        ativos.append({
            "id": linha[0],     # CORRIGIDO: Removido o 'linea_id :=' por completo
            "ticker": linha[1],
            "tipo": linha[2],  
            "qtd": linha[3],
            "preco": linha[4],
            "total": linha[3] * linha[4]
        })
    return jsonify(ativos)

@app.route('/api/carteira', methods=['POST'])
def adicionar_ativo():
    dados_recebidos = request.json
    ticker = dados_recebidos.get('ticker', '').upper().strip()
    tipo = dados_recebidos.get('tipo')
    qtd = int(dados_recebidos.get('qtd', 0))
    preco = float(dados_recebidos.get('preco', 0.0))
    
    if ticker and tipo and qtd > 0 and preco > 0:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO carteira (ticker, tipo, qtd, preco) VALUES (?, ?, ?, ?)",
            (ticker, tipo, qtd, preco)
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso"}), 201
    return jsonify({"status": "erro"}), 400


# ----------------- ROTA COM O MOTOR GROQ (LLAMA 3.3) -----------------

@app.route('/api/analise-ia', methods=['POST'])
def analisar_com_ia():
    dados_requisicao = request.json
    ticker_alvo = dados_requisicao.get('ticker', '').upper().strip()
    perfil_usuario = dados_requisicao.get('perfil', 'Moderado')
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, tipo, qtd FROM carteira")
    carteira_usuario = cursor.fetchall()
    conn.close()
    
    texto_carteira = ", ".join([f"{item[0]} ({item[1]}, Qtd: {item[2]})" for item in carteira_usuario])
    if not texto_carteira:
        texto_carteira = "Nenhum investimento cadastrado ainda."
        
    macro = buscar_dados_economia()
    
    prompt = f"""
    Você é um Analista de Mercado Financeiro sênior e um consultor quantitativo de alta performance.
    Dê um diagnóstico sincero, educativo e focado em valor sobre o ativo: {ticker_alvo}.
    
    CONTEXTO ATUAL DO MERCADO BRASILEIRO:
    - Ibovespa: {macro['ibovespa']['valor']} pontos (Variação: {macro['ibovespa']['variacao']}%)
    - Dólar Comercial: R$ {macro['dolar']['valor']}
    - Taxa Selic Meta: {macro['selic']}
    - Inflação IPCA: {macro['ipca']}
    
    DADOS DO INVESTIDOR:
    - Perfil de Risco: {perfil_usuario}
    - Carteira Atual dele: [{texto_carteira}]
    
    REGRAS DE RESPOSTA:
    1. Responda em português claro, direto, sem jargões excessivos (traduza o economês).
    2. Avalie se o ativo {ticker_alvo} se encaixa bem no perfil '{perfil_usuario}' e considerando a carteira atual dele.
    3. Dê uma recomendação clara (ex: Compra sugerida, Atenção/Aguardar, Fora do Perfil).
    4. Formate a resposta como um relatório técnico limpo e use espaçamentos. Não use HTML na resposta, use estilo terminal.
    """
    
    try:
        resposta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Você é um analista financeiro profissional brasileiro."},
                {"role": "user", "content": prompt}
            ]
        )
        
        texto_analise = resposta.choices[0].message.content
        
        return jsonify({
            "status": "sucesso",
            "analise": texto_analise
        })
    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": f"Erro interno ao chamar a API do Groq: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True)