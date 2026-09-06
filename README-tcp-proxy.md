# 🔌 TCP Proxy + SSL Client — Python Network Toolkit

> **Context:** Network security toolkit built from scratch in pure Python stdlib — a raw TCP proxy with hexdump traffic inspection and an SSL/TLS-aware client. Developed to understand low-level socket communication, protocol analysis, and traffic interception without relying on third-party libraries.

---

## `$ cat ./objective.txt`

Build a **protocol-agnostic TCP proxy** capable of:

- Intercepting traffic between a local client and any remote host
- Visualizing raw payloads in real-time as **hexdump** (offset + hex + printable)
- Exposing hooks for **on-the-fly packet modification** (request and response)
- Handling multiple simultaneous connections via **threading**

Paired with a **raw SSL/TLS TCP client** that communicates at socket level — bypassing abstractions like `requests` or `urllib` to expose the full protocol stack.

---

## `$ ls -la`

```
tcp-proxy-toolkit/
├── Proxy_TCP.py     # Core proxy — intercepts, inspects, and forwards TCP traffic
├── Cliente_TCP.py   # Raw TCP client with SSL/TLS wrapping
└── README.md
```

**Zero dependências externas** — apenas stdlib Python 3.6+.

---

## `$ cat ./architecture.txt`

### Fluxo de dados — TCP Proxy

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          PROXY ARCHITECTURE                              │
│                                                                          │
│  CLIENT              LOCAL SOCKET            REMOTE SOCKET    SERVER     │
│  (browser,  ───────► [localhost:port]  ────► [remote:port] ──► (any     │
│   tool...)           │                       │                  TCP      │
│                      │                       │                  service) │
│                ┌─────▼──────┐          ┌─────▼──────┐                   │
│                │  request_  │          │  response_ │                   │
│                │  handler() │          │  handler() │                   │
│                └─────┬──────┘          └─────┬──────┘                   │
│                      │    hexdump()           │                          │
│                      └───────────────────────┘                          │
│                             [live inspection]                            │
└──────────────────────────────────────────────────────────────────────────┘

 →  Client ══► Proxy ══► Server    [request_handler]   inspeciona e modifica
 ←  Client ◄══ Proxy ◄══ Server    [response_handler]  inspeciona e modifica
```

---

## `$ cat ./components.md`

### 1. `hexdump()` — Inspeção de payload em tempo real

Protocolos TCP são binários — imprimir o buffer raw como string produz output ilegível para dados não-ASCII (TLV, binários, protocolos proprietários). O hexdump exibe **três colunas simultâneas**:

```
0000  47 45 54 20 2F 20 48 54 54 50 2F 31 2E 31 0D 0A  GET / HTTP/1.1..
0010  48 6F 73 74 3A 20 65 78 61 6D 70 6C 65 2E 63 6F  Host: example.co
0020  6D 0D 0A 43 6F 6E 6E 65 63 74 69 6F 6E 3A 20 63  m..Connection: c
```

| Coluna | Conteúdo | Uso |
|--------|----------|-----|
| `0000` | Offset em hex | Localizar posição exata no buffer |
| `47 45 54...` | Bytes em hexadecimal | Magic bytes, delimitadores, valores binários |
| `GET / HTTP...` | Caracteres imprimíveis (`.` para não-printable) | Leitura humana do payload |

**Como o `HEX_FILTER` funciona:**

```python
HEX_FILTER = ''.join(
    ([len(repr(chr(i))) == 3] and chr(i) or '.') for i in range(256)
)
```

`repr(chr(i))` retorna `'x'` (3 chars) para printáveis e `'\\xNN'` (mais de 3) para não-printáveis. O `len == 3` funciona como seletor sem if/else explícito — uma lista `[True]` é truthy e retorna `chr(i)`; `[False]` é falsy e cai no `or '.'`.

---

### 2. `receive_from()` — Recepção com timeout

TCP é um protocolo de **stream** — não existe garantia de que uma mensagem chegue em um único `recv()`. Sem timeout, o socket bloquearia esperando mais dados mesmo após a resposta completa ter chegado.

```python
connection.settimeout(5)  # 5s — aumentar para redes com alta latência
```

O loop acumula chunks em `buffer` até o remote fechar a conexão (`not data`) ou o timeout estourar — o que vier primeiro.

---

### 3. `request_handler()` / `response_handler()` — Hooks de modificação

Dois pontos de interceptação distintos no pipeline:

```python
def request_handler(buffer):
    # Client → Server: modificar antes de enviar ao remote
    # Ex: buffer = buffer.replace(b'HTTP/1.1', b'HTTP/1.0')
    return buffer

def response_handler(buffer):
    # Server → Client: modificar antes de enviar ao cliente local
    # Ex: buffer = buffer.replace(b'Content-Encoding: gzip', b'')
    return buffer
```

Esse padrão é a base de ferramentas como **Burp Suite** e **mitmproxy** — separar os handlers permite modificar apenas requests, apenas responses, ou ambos de forma independente.

---

### 4. `proxy_handler()` — Loop bidirecional + `receive_first`

O flag `receive_first` resolve um problema real de protocolos **server-initiated**: em FTP, SMTP e outros serviços, o servidor envia um banner *antes* de receber qualquer dado do cliente.

```
receive_first=True:   Proxy lê o banner do servidor → repassa ao cliente
receive_first=False:  Proxy espera o cliente falar primeiro (ex: HTTP)
```

**Loop principal corrigido:**

```
1. Recebe dados do cliente local
2. hexdump() + request_handler()
3. Envia ao servidor remoto
4. Recebe resposta do servidor remoto     ← estava faltando na versão original
5. hexdump() + response_handler()
6. Repassa ao cliente local
7. Se ambos os lados sem dados → fecha conexões
```

---

### 5. `server_loop()` — Thread por conexão

```python
proxy_thread = threading.Thread(
    target=proxy_handler,
    args=(client_socket, remote_host, remote_port, receive_first),
    daemon=True
)
proxy_thread.start()
```

Cada nova conexão recebe uma **thread dedicada** — o servidor principal continua em `accept()` enquanto as threads existentes processam seu tráfego. `daemon=True` garante que as threads não impeçam o encerramento limpo do processo.

---

### 6. `Cliente_TCP.py` — Raw SSL/TLS socket

Bibliotecas de alto nível abstraem o handshake TLS, headers HTTP e gestão de conexão. O cliente raw expõe cada camada individualmente:

```python
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # Socket TCP puro
context = ssl.create_default_context()                   # TLS 1.2+ moderno
s_sock = context.wrap_socket(s, server_hostname=host)   # TLS wrapping
s_sock.connect((host, 443))                             # TCP + TLS handshake
s_sock.send(b"GET / HTTP/1.1\r\nHost: ...\r\n\r\n")    # HTTP manual
```

Isso permite testar serviços não-HTTP na porta 443, enviar payloads arbitrários (fuzzing, protocol testing), e desenvolver clientes para protocolos proprietários.

---

## `$ diff ./original ./fixed`

Bugs identificados e corrigidos:

```diff
Proxy_TCP.py

- import socketserver                     # import não utilizado, removido
+ # (removido)

- if len(sys.args[1:]) != 5:             # BUG: sys.args não existe → AttributeError
+ if len(sys.argv[1:]) != 5:             # FIX: sys.argv

- remote_buffer = response_handler(...)  # BUG: UnboundLocalError se receive_first=False
+ remote_buffer = b""                    # FIX: inicializar antes do bloco condicional

  while True:
      local_buffer = receive_from(client_socket)
      ...
      remote_socket.send(local_buffer)
-     # BUG: nunca lê a resposta do remote dentro do loop
-     # remote_buffer ficava com valor da iteração anterior, proxy não repassava respostas
+     remote_buffer = receive_from(remote_socket)   # FIX: receber e repassar a resposta
+     if len(remote_buffer):
+         client_socket.send(remote_buffer)

-     if not len(local_buffer) or not len(remote_buffer):  # BUG: 'or' fecha precocemente
+     if not len(local_buffer) and not len(remote_buffer): # FIX: 'and' — fecha só quando ambos vazios

- receive_first = sys.argv[5].strip().lower() in ["true"]  # forma frágil
+ receive_first = sys.argv[5].strip().lower() == "true"    # comparação explícita

────────────────────────────────────────────────────────

Cliente_TCP.py

- context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)  # BUG: deprecated + nunca utilizado
- s_sock = ssl.create_default_context().wrap_socket(...)  # criava contexto descartável
+ context = ssl.create_default_context()         # FIX: um único contexto moderno (TLS 1.2+)
+ s_sock = context.wrap_socket(s, server_hostname=target_host)

- s_sock.send(b"GET / http/1.1/r/nHost: DOMAIN-TARGET/r/n/r/n")
+ s_sock.send(                                   # FIX: \r\n real (CRLF conforme RFC 7230)
+     f"GET / HTTP/1.1\r\n"                      # FIX: HTTP/1.1 maiúsculo
+     f"Host: {target_host}\r\n"                 # FIX: usar variável, não string hardcoded
+     f"Connection: close\r\n\r\n"
+     .encode()
+ )
```

---

## `$ cat ./usage.sh`

### Proxy TCP

```bash
# Sintaxe
python Proxy_TCP.py [localhost] [localport] [remotehost] [remoteport] [receive_first]

# Interceptar HTTP — redirecionar para exemplo.com:80
python Proxy_TCP.py 127.0.0.1 8080 exemplo.com 80 False

# Interceptar FTP — servidor envia banner primeiro
python Proxy_TCP.py 127.0.0.1 2121 ftp.alvo.com 21 True
```

```
# Output esperado (HTTP):
[*] Proxy ouvindo em 127.0.0.1:8080
[*] Encaminhando para exemplo.com:80
[>] Conexão recebida de 127.0.0.1:54321
[==>] Recebido 78 bytes do cliente local.
0000  47 45 54 20 2F 20 48 54 54 50 2F 31 2E 31 0D 0A  GET / HTTP/1.1..
...
[<==] Recebido 1024 bytes do remote.
0000  48 54 54 50 2F 31 2E 31 20 32 30 30 20 4F 4B 0D  HTTP/1.1 200 OK.
...
```

### Cliente TCP/SSL

```bash
# Editar target_host no arquivo
python Cliente_TCP.py

# Output esperado:
[*] Conectado a example.com:443
[*] Protocolo TLS negociado: TLSv1.3
[==>] Request enviado: GET / HTTP/1.1 ...
[<==] Resposta: HTTP/1.1 200 OK ...
```

---

## `$ cat ./extensions.md`

| Feature | Técnica | Caso de uso |
|---------|---------|-------------|
| SSL stripping | `wrap_socket()` apenas no lado cliente | Inspecionar HTTPS em plain text |
| Log para arquivo | `logging` + rotation | Captura persistente de sessões |
| Regex modifier | `re.sub()` nos handlers | Substituição automática em respostas |
| SOCKS5 support | RFC 1928 | Proxy genérico para qualquer protocolo |
| Async I/O | `asyncio` + `StreamReader/Writer` | Alta concorrência sem overhead de threads |
| Packet replay | Serializar buffers em disco | Reproduzir requisições capturadas |

---

## `$ cat ./concepts.md`

**TCP Socket Lifecycle:**
`socket()` → `bind()` → `listen()` → `accept()` → `recv()/send()` → `close()`

**TLS Handshake (simplificado):**
`TCP connect` → `ClientHello` → `ServerHello + Certificate` → `Key Exchange` → `Finished` → `Application Data`

**Hexdump:** Representação de dados binários em base 16 com coluna de caracteres imprimíveis — padrão em análise de protocolos, forense e debugging de rede (Wireshark, xxd, tcpdump).

**Thread per connection:** Modelo simples de concorrência — cada conexão recebe uma thread. Adequado para baixa concorrência. Para escala, modelos event-driven (`select`, `epoll`, `asyncio`) são mais eficientes.

**CRLF (`\r\n`):** HTTP exige *Carriage Return + Line Feed* como terminador de linha conforme RFC 7230. `\r\n` em Python é o escape correto — `/r/n` é a string literal de 4 caracteres `/`, `r`, `/`, `n`.

---

<p align="center">
  <i>Built from scratch · Zero third-party dependencies · Pure Python 3 stdlib</i>
</p>
