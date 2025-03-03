import json
from autobahn.twisted.websocket import WebSocketServerFactory, \
     WebSocketServerProtocol
from jmbitcoin import human_readable_transaction
from jmbase import get_log

jlog = get_log()

class JmwalletdWebSocketServerProtocol(WebSocketServerProtocol):
    def onOpen(self):
        self.token = None
        self.factory.register(self)

    def sendNotification(self, info):
        """ Passes on an object (json encoded) to the client,
        if currently authenticated.
        """
        if not self.token:
            # gating by token means even if this client
            # is erroneously in a broadcast list, it won't get
            # any data if it hasn't authenticated.
            jlog.warn("Websocket not sending notification, "
                      "the connection is not authenticated.")
            return
        self.sendMessage(json.dumps(info).encode())

    def connectionLost(self, reason):
        """ Overridden to ensure that we aren't attempting to
        send notifications on broken connections.
        """
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)

    def onMessage(self, payload, isBinary):
        """ We currently only allow messages which
        are JWT tokens used for authentication. Any
        other message will drop the connection.
        """
        if not isBinary:
            self.token = payload.decode('utf8')
            # check that the token set for this protocol
            # instance is the same as the one that the
            # JMWalletDaemon instance deems is valid.
            if not self.factory.check_token(self.token):
                self.dropConnection()

class JmwalletdWebSocketServerFactory(WebSocketServerFactory):
    def __init__(self, url):
        WebSocketServerFactory.__init__(self, url)
        self.valid_token = None
        self.clients = []

    def check_token(self, token):
        return self.valid_token == token

    def register(self, client):
        if client not in self.clients:
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            self.clients.remove(client)

    def sendTxNotification(self, txd, txid):
        """ Note that this is a WalletService callback;
        the return value is only important for conf/unconf
        callbacks, not for 'all' callbacks, so we return
        None
        """
        json_tx = json.loads(human_readable_transaction(txd))
        for client in self.clients:
            client.sendNotification({"txid": txid,
            "txdetails": json_tx})

    def sendCoinjoinStatusUpdate(self, new_state):
        """ The state sent is an integer, see
        jmclient.wallet_rpc.
        0: taker is running
        1: maker is running (but not necessarily currently
           coinjoining, note)
        2: neither is running
        """
        for client in self.clients:
            client.sendNotification({"coinjoin_state": new_state})
