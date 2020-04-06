import socket
import ssl
import enum
try:
    import hyperframe.frame
except:
    exit('install "hyperframe" from pip')
try:
    import hpack
except:
    exit('install "hpack" from pip')

MAGIC = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'


class ErrorCode(enum.Enum):
    NO_ERROR = 0
    PROTOCOL_ERROR = 1
    INTERNAL_ERROR = 2
    FLOW_CONTROL_ERROR = 3
    SETTINGS_TIMEOUT = 4
    STREAM_CLOSED = 5
    FRAME_SIZE_ERROR = 6
    REFUSED_STREAM = 7
    CANCEL = 8
    COMPRESSION_ERROR = 9
    CONNECT_ERROR = 10
    ENHANCE_YOUR_CALM = 11
    INADEQUATE_SECURITY = 12
    HTTP_1_1_REQUIRED = 13


class Settings(enum.Enum):
    HEADER_TABLE_SIZE = 1
    ENABLE_PUSH = 2
    MAX_CONCURRENT_STREAMS = 3
    INITIAL_WINDOW_SIZE = 4
    MAX_FRAME_SIZE = 5
    MAX_HEADER_LIST_SIZE = 6


def connect(hostname):
    '''Returns socket with secure h2 connection'''
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.set_alpn_protocols(['h2'])
    sock = socket.create_connection((hostname, 443))
    sock = ssl_ctx.wrap_socket(sock, server_hostname=hostname)
    assert sock.selected_alpn_protocol() == 'h2'
    return sock


def write(sock, data):
    '''Send data (h2 frame or raw bytes)'''
    if isinstance(data, hyperframe.frame.Frame):
        print("> ", data)
        data = data.serialize()
    else:
        print("> ", data)

    sock.sendall(data)


def read_bytes(sock, num_bytes):
    '''Read exact number of bytes from socket'''
    data = b''
    while len(data) < num_bytes:
        rcv = sock.recv(num_bytes - len(data))
        if not rcv:
            exit('connection over')
        data += rcv
    return data


def read_frame(sock):
    '''Read exactly 1 h2 frame from socket '''
    data = read_bytes(sock, 9)
    frame, payload_len = hyperframe.frame.Frame.parse_frame_header(data)
    if payload_len:
        data = read_bytes(sock, payload_len)
        frame.parse_body(memoryview(data))

    return frame


if __name__ == '__main__':
    # connect
    hostname = 'www.google.com'
    hpack_enc = hpack.Encoder()
    hpack_dec = hpack.Decoder()
    sock = connect(hostname)

    # send connection preface
    write(sock, MAGIC)
    write(sock, hyperframe.frame.SettingsFrame())

    # send request
    headers = hyperframe.frame.HeadersFrame(3)
    headers.data = hpack_enc.encode([
        (b':method', b'GET'),
        (b':scheme', b'https'),
        (b':authority', b'www.google.com'),
        (b':path', b'/'),
    ])
    headers.flags.add('END_HEADERS')
    headers.flags.add('END_STREAM')
    write(sock, headers)

    # read frames
    while True:
        frame = read_frame(sock)
        print("< ", frame, 'body_len:', frame.body_len)
        if isinstance(frame, hyperframe.frame.HeadersFrame):
            print('   ', hpack_dec.decode(frame.data))

        if isinstance(frame, hyperframe.frame.DataFrame):
            if len(frame.data) < 70:
                print('    {}'.format(frame.data))
            else:
                print('    {}...'.format(frame.data[:70]))

        if isinstance(frame, hyperframe.frame.GoAwayFrame):
            print('    error_code:{} last_stream_id:{}'.format(
                ErrorCode(frame.error_code).name, frame.last_stream_id))

        if isinstance(frame, hyperframe.frame.RstStreamFrame):
            print('    error_code:{}'.format(ErrorCode(frame.error_code).name))

        if isinstance(frame, hyperframe.frame.SettingsFrame) and not 'ACK' in frame.flags:
            print('   ', {Settings(k).name: v for k,
                          v in frame.settings.items()})
