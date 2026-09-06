import socket
import ssl

target_host = "example.com"  # Substituir pelo host alvo
target_port = 443

# FIX: remover ssl.SSLContext(ssl.PROTOCOL_TLSv1) — deprecated desde Python 3.10
# e nunca era utilizado (create_default_context() já cria o contexto correto abaixo)

# Criar socket TCP puro
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Envolver com TLS usando o contexto padrão seguro (TLS 1.2+ negociado automaticamente)
context = ssl.create_default_context()
s_sock = context.wrap_socket(s, server_hostname=target_host)

# Estabelecer conexão (TCP handshake + TLS handshake)
s_sock.connect((target_host, target_port))
print(f"[*] Conectado a {target_host}:{target_port}")
print(f"[*] Protocolo TLS negociado: {s_sock.version()}")

# FIX: /r/n → \r\n  (HTTP requer CRLF como line ending, não a string literal "/r/n")
# FIX: http/1.1 → HTTP/1.1  (protocolo deve ser maiúsculo conforme RFC 7230)
# FIX: usar a variável target_host no header Host em vez de string hardcoded
request = (
    f"GET / HTTP/1.1\r\n"
    f"Host: {target_host}\r\n"
    f"Connection: close\r\n"
    f"\r\n"
)
s_sock.send(request.encode())
print(f"[==>] Request enviado:\n{request}")

# Receber resposta completa
print("[<==] Resposta:")
while True:
    data = s_sock.recv(4096)
    if len(data) < 1:
        break
    print(data.decode(errors='replace'))

s_sock.close()
print("[*] Conexão encerrada.")
