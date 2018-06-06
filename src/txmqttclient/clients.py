"""
Copyright 2018 Jason Litzinger
See LICENSE for details.
"""
from __future__ import absolute_import

import binascii

from twisted.internet import ssl, endpoints, reactor, protocol, task, defer
from twisted.logger import Logger
import mqttpacket.v311 as mqttpacket

defer.setDebugging(True)

_logMQTT = True


class MQTTClient(protocol.Protocol):
    """
    A client for an MQTT Broker.
    """
    log = Logger()

    def __init__(self, client_id):
        self.client_id = client_id
        self._incoming = bytearray()
        self._connack_d = defer.Deferred()
        self._maintenance = None

    def connect(self):
        """Send a CONNECT to the broker.

        :returns: Deferred that will fire when the broker connects
            or will error if the connection is terminated.
        """
        self.log.info('Connect to broker')
        connpkt = mqttpacket.connect(self.client_id)
        if _logMQTT:
            self.log.info("Connect: {bdata}", bdata=binascii.hexlify(connpkt))

        self.transport.write(connpkt)
        return self._connack_d

    def connectionMade(self):
        self.log.info("Protocol Connected")

    def connectionLost(self, reason=protocol.connectionDone):
        self.log.warn(
            "Connection dropped: {reason}",
            reason=reason.getErrorMessage()
        )
        if not self._connack_d.called:
            self._connack_d.errback(reason)

    def logPrefix(self):
        return "mqttclient"

    def _send_ping(self):
        msg = mqttpacket.pingreq()
        self.transport.write(msg)

    def _start_maintenance(self):
        self._maintenance = task.LoopingCall(self._send_ping)
        self._maintenance.start(20, now=False)

    def dataReceived(self, data):
        if _logMQTT:
            self.log.info("Data: {bdata}", bdata=binascii.hexlify(data))
        self._incoming.extend(data)
        packets = []
        consumed = mqttpacket.parse(self._incoming, packets)
        if _logMQTT:
            self.log.info('Consumed {cons}', cons=consumed)

        for packet in packets:
            self.log.debug('Received packet {pkt}', pkt=packet)
            if packet.pkt_type == mqttpacket.MQTT_PACKET_CONNACK:
                if not self._connack_d.called:
                    self._connack_d.callback(self)
                    self._start_maintenance()

        self._incoming = self._incoming[consumed:]

    def subscribe(self, topic):
        """Subscribe to the provided topicfilters

        :param topic: The topic to subscribe to.
        :type topic: text

        """
        tfs = [
            mqttpacket.SubscriptionSpec(topic, 0)
        ]
        subscription = mqttpacket.subscribe(1, tfs)
        if _logMQTT:
            self.log.info(
                'Subscribe: {subs}',
                subs=binascii.hexlify(subscription)
            )
        self.transport.write(subscription)

    def publish(self, topic, message):
        # (str, bytes) -> None
        """Publish a message on a topic."""
        if not isinstance(message, bytes):
            raise TypeError('message must be bytes')

        msg = mqttpacket.publish(topic, False, 0, False, message)
        if _logMQTT:
            self.log.info(
                'Publish: {pub}',
                pub=binascii.hexlify(msg)
            )
        self.transport.write(msg)


def connect_mqtt_tls(client_id, host, rootpath, port, client_creds=None):
    """Connect an MQTT Client over TLS without client auth.

    :param host: The hostname to connect
    :type host: str

    :param rootpath: Path to the root certificate
    :type rootpath: str

    :param port (optional): The port to use, default 8883
    :type port: int

    :param client_creds: Client cert/key pair
    :type client_creds: ssl.PrivateCertificate

    """
    with open(rootpath, 'rb') as rootf:
        rootblob = rootf.read()

    trust_root = ssl.trustRootFromCertificates(
        [ssl.Certificate.loadPEM(rootblob)]
    )

    tls_options = ssl.optionsForClientTLS(
        host,
        trustRoot=trust_root,
        clientCertificate=client_creds,
    )

    endpoint = endpoints.SSL4ClientEndpoint(
        reactor,
        host,
        port,
        tls_options
    )

    d = endpoints.connectProtocol(
        endpoint,
        MQTTClient(client_id)
    )

    def _socket_connected(client):
        return client.connect()

    d.addCallback(_socket_connected)
    return d
