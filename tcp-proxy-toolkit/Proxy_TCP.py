import sys
import threading
import socket

# HEX_FILTER mapeia cada um dos 256 valores ASCII:
# - chr(i) se for caractere imprimível (repr tem exatamente 3 chars: aspas + char + aspas)
# - '.' caso contrário (caracteres de controle, não-ASCII, etc.)
HEX_FILTER = ''.join(
    ([len(repr(chr(i))) == 3] and chr(i) or '.') for i in range(256)
)

def hexdump(src, length=16, show=True):
    """Exibe o buffer como hexdump: offset | bytes em hex | caracteres imprimíveis."""
    if isinstance(src, bytes):
        src = src.decode(errors='replace')
    results = []
    for i in range(0, len(src), length):
        word = str(src[i:i + length])
        printable = word.translate(HEX_FILTER)
        hexa = ' '.join([f'{ord(c):02X}' for c in word])
        hexwidth = length * 3
        results.append(f'{i:04X}  {hexa:<{hexwidth}}  {printable}')
    if show:
        for line in results:
            print(line)
    else:
        return results


def receive_from(connection):
    """Acumula dados do socket até timeout ou fechamento da conexão."""
    buffer = b""
    connection.settimeout(5)  # Aumentar para redes com alta latência (ex: VPN internacional)
    try:
        while True:
            data = connection.recv(4096)
            if not data:
                break
            buffer += data
    except Exception:
        pass
    return buffer


def request_handler(buffer):
    """Hook para modificar pacotes Client → Server antes do envio ao remote."""
    # Exemplo de uso: buffer = buffer.replace(b'HTTP/1.1', b'HTTP/1.0')
    return buffer


def response_handler(buffer):
    """Hook para modificar pacotes Server → Client antes do envio ao cliente local."""
    # Exemplo de uso: buffer = buffer.replace(b'Content-Encoding: gzip', b'')
    return buffer


def proxy_handler(client_socket, remote_host, remote_port, receive_first):
    """Gerencia o tráfego bidirecional entre cliente local e host remoto."""
    remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    remote_socket.connect((remote_host, remote_port))

    # FIX: inicializar remote_buffer antes do bloco condicional
    # evita UnboundLocalError quando receive_first=False
    remote_buffer = b""

    # Alguns protocolos (FTP, SMTP) enviam banner antes de receber qualquer dado
    if receive_first:
        remote_buffer = receive_from(remote_socket)
        hexdump(remote_buffer)
        remote_buffer = response_handler(remote_buffer)
        if len(remote_buffer):
            print(f"[<==] Enviando {len(remote_buffer)} bytes ao cliente local.")
            client_socket.send(remote_buffer)

    while True:
        # Recebe dados do cliente local
        local_buffer = receive_from(client_socket)
        if len(local_buffer):
            print(f"[==>] Recebido {len(local_buffer)} bytes do cliente local.")
            hexdump(local_buffer)
            local_buffer = request_handler(local_buffer)
            remote_socket.send(local_buffer)
            print(f"[==>] Encaminhado ao remote {remote_host}:{remote_port}.")

        # FIX: receber resposta do remote a cada iteração do loop
        # sem isso, remote_buffer nunca é atualizado e o proxy não repassa respostas
        remote_buffer = receive_from(remote_socket)
        if len(remote_buffer):
            print(f"[<==] Recebido {len(remote_buffer)} bytes do remote.")
            hexdump(remote_buffer)
            remote_buffer = response_handler(remote_buffer)
            client_socket.send(remote_buffer)
            print(f"[<==] Encaminhado ao cliente local.")

        # FIX: usar 'and' em vez de 'or'
        # com 'or': fecha a conexão assim que qualquer lado não tem dados (falso positivo)
        # com 'and': fecha apenas quando ambos os lados estão sem dados
        if not len(local_buffer) and not len(remote_buffer):
            client_socket.close()
            remote_socket.close()
            print("[*] Sem dados em ambos os lados. Conexões encerradas.")
            break


def server_loop(local_host, local_port, remote_host, remote_port, receive_first):
    """Inicia o servidor e despacha cada conexão para uma thread dedicada."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((local_host, local_port))
    except Exception as e:
        print(f"[!!] Falha ao fazer bind em {local_host}:{local_port} — {e}")
        print("[!!] Verifique se a porta está em uso ou se há permissão necessária.")
        sys.exit(1)

    print(f"[*] Proxy ouvindo em {local_host}:{local_port}")
    print(f"[*] Encaminhando para {remote_host}:{remote_port}")
    server.listen(5)

    while True:
        client_socket, addr = server.accept()
        print(f"[>] Conexão recebida de {addr[0]}:{addr[1]}")
        proxy_thread = threading.Thread(
            target=proxy_handler,
            args=(client_socket, remote_host, remote_port, receive_first),
            daemon=True
        )
        proxy_thread.start()


def main():
    # FIX: sys.args → sys.argv (sys.args não existe — AttributeError em runtime)
    if len(sys.argv[1:]) != 5:
        print("Uso:    python proxy.py [localhost] [localport] [remotehost] [remoteport] [receive_first]")
        print("Exemplo: python proxy.py 127.0.0.1 8080 exemplo.com 80 False")
        print("         python proxy.py 127.0.0.1 2121 ftp.alvo.com 21 True")
        sys.exit(0)

    local_host  = sys.argv[1]
    local_port  = int(sys.argv[2])
    remote_host = sys.argv[3]
    remote_port = int(sys.argv[4])
    receive_first = sys.argv[5].strip().lower() == "true"

    server_loop(local_host, local_port, remote_host, remote_port, receive_first)


if __name__ == '__main__':
    main()
