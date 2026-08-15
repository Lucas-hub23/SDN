"""
Campus SDN Topologie van gebouw A & B in opdracht van het CVB
"""
from functools import partial
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.nodelib import NAT
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

FAUCET_IP = "192.168.56.20"

# Transit
NAT_V4 = '10.99.0.10'          # natNode, gebouw A
ISP_V4 = '10.99.0.20'          # ispNode, gebouw B
ISP_V6 = '2001:db8:99::20'
TRANSIT_V4GW = '10.99.0.1'     # Faucet-VIP op het transit-VLAN
TRANSIT_V6GW = '2001:db8:99::1' 

# Gesimuleerde internet-hosts, achter de uplink-nodes.
NET_V4_SUBNET = '203.0.113.0/24'
NET_V4_ISP = '203.0.113.1'     # kant van de natNode
NET_V4_HOST = '203.0.113.50'   # de "internet"-host
NET_V6_SUBNET = '2001:db8:ff::/64'
NET_V6_ISP = '2001:db8:ff::1'  # kant van de ispNode
NET_V6_HOST = '2001:db8:ff::50'

# Adresplan
BUILDINGS = {
    'A': {
        'floors': [('A1', 11), ('A2', 12)],
        'emp': {'v4': '10.10.0.%d/24', 'v4gw': '10.10.0.1',
                'v6': '2001:db8:a:10::%d/64', 'v6gw': '2001:db8:a:10::1'},
        'gst': {'v4': '10.20.0.%d/24', 'v4gw': '10.20.0.1',
                'v6': '2001:db8:a:20::%d/64', 'v6gw': '2001:db8:a:20::1'},
        'mgt': {'v4': '10.30.0.%d/26', 'v4gw': '10.30.0.1',
                'v6': '2001:db8:a:30::%d/64', 'v6gw': '2001:db8:a:30::1'},
    },
    'B': {
        'floors': [('B1', 13), ('B2', 14), ('B3', 15)],
        'emp': {'v4': '10.11.0.%d/24', 'v4gw': '10.11.0.1',
                'v6': '2001:db8:b:10::%d/64', 'v6gw': '2001:db8:b:10::1'},
        'gst': {'v4': '10.21.0.%d/24', 'v4gw': '10.21.0.1',
                'v6': '2001:db8:b:20::%d/64', 'v6gw': '2001:db8:b:20::1'},
        'mgt': {'v4': '10.31.0.%d/26', 'v4gw': '10.31.0.1',
                'v6': '2001:db8:b:30::%d/64', 'v6gw': '2001:db8:b:30::1'},
    },
}

# Alle interne subnetten
V4_SUBNETS = ('10.10.0.0/24', '10.20.0.0/24', '10.30.0.0/26',
              '10.11.0.0/24', '10.21.0.0/24', '10.31.0.0/26')
V6_SUBNETS = ('2001:db8:a:10::/64', '2001:db8:a:20::/64', '2001:db8:a:30::/64',
              '2001:db8:b:10::/64', '2001:db8:b:20::/64', '2001:db8:b:30::/64')


class CampusTopo(Topo):
    def build(self):
        #  Switches
        sA_core = self.addSwitch('sA_core', dpid='0000000000000001')
        sA1 = self.addSwitch('sA1', dpid='0000000000000002')
        sA2 = self.addSwitch('sA2', dpid='0000000000000003')
        sB_core = self.addSwitch('sB_core', dpid='0000000000000004')
        sB1 = self.addSwitch('sB1', dpid='0000000000000005')
        sB2 = self.addSwitch('sB2', dpid='0000000000000006')
        sB3 = self.addSwitch('sB3', dpid='0000000000000007')

        # Uplink gebouw A: NAT-node voor IPv4
        # inNamespace=False -> deelt de root-namespace van de VM en ziet
        # daardoor de echte eth0.
        nat = self.addNode('natNode', cls=NAT, ip='%s/24' % NAT_V4,
                           subnet='10.0.0.0/8', inNamespace=False)

        # Uplink gebouw B: ISP-node voor IPv6
        # Gewone host in een EIGEN namespace eigen routetabel en eigen
        # ip6tables dus los van de VM.
        isp = self.addHost('ispNode', ip='%s/24' % ISP_V4)

        # Gesimuleerde internet-hosts, achter de uplink-nodes.
        # Staan buiten de OpenFlow-topologie vanuit de campus gezien
        # zijn dit hosts "op internet".
        netA = self.addHost('netA')   # achter natNode, IPv4
        netB = self.addHost('netB')   # achter ispNode, IPv6

        # Switch/stacklinks
        # Poortnummers EXPLICIET Mininet nummert anders op volgorde van
        # aanmaken, deze manier matcht met faucet.yaml.
        self.addLink(sA1, sA_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sA2, sA_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB1, sB_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sB2, sB_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB3, sB_core, port1=1, port2=3, cls=TCLink, bw=1000)

        # Darkfiber: sA_core p3 <-> sB_core p4
        self.addLink(sA_core, sB_core, port1=3, port2=4,
                     cls=TCLink, bw=1000, delay='5ms')

        # Uplinks naar de switches
        self.addLink(nat, sA_core, port2=4)
        self.addLink(isp, sB_core, port2=5)

        # Uplinks naar de internet-hosts
        self.addLink(nat, netA)
        self.addLink(isp, netB)

        # Hosts per verdieping emp, gst en mgt
        switches = {'A1': sA1, 'A2': sA2, 'B1': sB1, 'B2': sB2, 'B3': sB3}
        for cfg in BUILDINGS.values():
            for tag, n in cfg['floors']:
                sw = switches[tag]
                for i, cat in enumerate(('emp', 'gst', 'mgt')):
                    host = self.addHost('h%s_%s' % (tag, cat),
                                        ip=cfg[cat]['v4'] % n)
                    self.addLink(host, sw, port2=2 + i)   # emp=2, gst=3, mgt=4


def configure_hosts(net):
    "Dual-stack adressen en default gateways per host"
    info("\n*** Hosts configureren (dual-stack)...\n")
    for cfg in BUILDINGS.values():
        for tag, n in cfg['floors']:
            for cat in ('emp', 'gst', 'mgt'):
                host = net.get('h%s_%s' % (tag, cat))
                iface = '%s-eth0' % host.name
                host.cmd('ip route replace default via %s' % cfg[cat]['v4gw'])
                host.cmd('ip -6 addr add %s dev %s' % (cfg[cat]['v6'] % n, iface))
                host.cmd('ip -6 route replace default via %s' % cfg[cat]['v6gw'])


def configure_nat(net):
    "natNode: IPv4 NAT + stateful firewall. Draait in de root-namespace."
    info("*** natNode configureren (IPv4 uplink gebouw A)...\n")
    nat = net.get('natNode')
    nat.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Adres op de link naar de internet-host
    nat.cmd('ip addr add %s/24 dev natNode-eth1' % NET_V4_ISP)
    nat.cmd('ip link set natNode-eth1 up')

    # Interface onafhankelijke MASQUERADE per subnet. De -C check voorkomt
    # dubbele regels bij herstart: de root-namespace wordt niet opgeruimd
    # door net.stop(). Verkeer naar netA wordt NIET vertaald, anders is de
    # firewall niet te testen (de bron zou dan altijd de natNode lijken).
    for subnet in V4_SUBNETS:
        rule = ('-t nat POSTROUTING -s %s ! -d 10.0.0.0/8 ! -d %s '
                '-j MASQUERADE' % (subnet, NET_V4_SUBNET))
        nat.cmd('iptables -C %s 2>/dev/null || iptables -A %s' % (rule, rule))

    # Retourroutes naar de interne VLAN's via de Faucet-VIP op het transit-VLAN
    for subnet in V4_SUBNETS:
        nat.cmd('ip route replace %s via %s' % (subnet, TRANSIT_V4GW))

    # Stateful firewall IPv4
    # De conntrack-module in de kernel houdt bij welke verbindingen lopen:
    #   ESTABLISHED/RELATED = antwoord op iets van binnenuit -> accepts
    #   NEW vanaf de campus                                  -> accept (onthouden)
    #   Al het overige inkomend verkeer                      -> drop
    #
    #
    # dit past wel de FORWARD-chain van de HELE VM aan (root-namespace). Eventueel terugdraaien met sudo iptables -P FORWARD ACCEPT
    
    nat.cmd('iptables -F FORWARD')
    nat.cmd('iptables -P FORWARD DROP')
    nat.cmd('iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    nat.cmd('iptables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    for subnet in V4_SUBNETS:
        nat.cmd('iptables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                % subnet)


def configure_isp(net):
    "ispNode: IPv6 routing + stateful firewall. Eigen namespace."
    info("*** ispNode configureren (IPv6 uplink gebouw B)...\n")
    isp = net.get('ispNode')
    isp.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    isp.cmd('sysctl -w net.ipv4.ip_forward=1')

    isp.cmd('ip -6 addr add %s/64 dev ispNode-eth0 nodad' % ISP_V6)
    # Adres op de link naar de internet-host
    isp.cmd('ip -6 addr add %s/64 dev ispNode-eth1 nodad' % NET_V6_ISP)
    isp.cmd('ip link set ispNode-eth1 up')

    isp.cmd('sleep 2')

    # Statische neighbor-entry voor de Faucet-VIP.
    # Faucet beantwoordt de Neighbor Solicitation voor zijn eigen IPv6-VIP
    # niet betrouwbaar in gestackte opzet de entry zakt weg naar DELAY
    # en daarna FAILED, waarna de ispNode geen retourverkeer meer kan
    # versturen.
    isp.cmd('ip -6 neigh replace %s lladdr 0e:00:00:00:40:01 '
            'dev ispNode-eth0 nud permanent' % TRANSIT_V6GW)

    # Retourroutes naar de interne VLAN's via de Faucet-VIP
    for subnet in V6_SUBNETS:
        out = isp.cmd('ip -6 route replace %s via %s'
                      % (subnet, TRANSIT_V6GW))
        if out.strip():
            info("    !! route %s: %s" % (subnet, out))

    # Stateful firewall IPv6
    # Deze regels raken alleen de namespace van ispNode, niet de VM zoals bij natnode.
    isp.cmd('ip6tables -F FORWARD')
    isp.cmd('ip6tables -P FORWARD DROP')
    isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    # Neighbor Discovery moet altijd door, anders breekt IPv6 volledig
    for icmp6 in ('133', '134', '135', '136'):
        isp.cmd('ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -j ACCEPT' % icmp6)
    for subnet in V6_SUBNETS:
        isp.cmd('ip6tables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                % subnet)


def configure_internet_hosts(net):
    """
    netA en netB simuleren hosts op internet, achter de uplink-nodes.

    Ze zijn nodig om de stateful firewall te testen: verkeer van deze
    hosts naar de campus wordt door de uplink-node GEROUTEERD en raakt
    daarmee de FORWARD-chain. Verkeer dat de uplink-node zelf genereert
    gaat door OUTPUT en zou de firewall niet passeren - dat is waarom
    een ping vanaf natNode of ispNode geen geldige test is.
    """
    info("*** Internet-hosts configureren (netA/netB)...\n")

    netA = net.get('netA')
    # Mininet's standaardadres weg anders kiest Linux dat als bronadres
    netA.cmd('ip addr flush dev netA-eth0')
    netA.cmd('ip addr add %s/24 dev netA-eth0' % NET_V4_HOST)
    netA.cmd('ip link set netA-eth0 up')
    netA.cmd('ip route replace default via %s' % NET_V4_ISP)

    netB = net.get('netB')
    netB.cmd('ip addr flush dev netB-eth0')
    netB.cmd('ip -6 addr add %s/64 dev netB-eth0 nodad' % NET_V6_HOST)
    netB.cmd('ip link set netB-eth0 up')
    netB.cmd('sleep 2')
    netB.cmd('ip -6 route replace default via %s' % NET_V6_ISP)

def run():
    net = Mininet(
        topo=CampusTopo(),
        controller=lambda name: RemoteController(name, ip=FAUCET_IP, port=6653),
        switch=partial(OVSSwitch, protocols='OpenFlow13'),
        link=TCLink,
        waitConnected=True,
    )
    net.start()

    configure_hosts(net)
    configure_nat(net)
    configure_isp(net)
    configure_internet_hosts(net)

    # Faucet leert een host pas als die zelf verkeer verstuurt. Geen idee waarom.
    # Zonder deze stap is
    # cross-building connectiviteit onbetrouwbaar. subnet-route staat
    # er wel, maar de host-route met MAC ontbreekt tot de bestemming zich
    # heeft gemeld.
    info("*** Netwerk opwarmen (hosts laten leren)...\n")
    for cfg in BUILDINGS.values():
        for tag, n in cfg['floors']:
            for cat in ('emp', 'gst', 'mgt'):
                host = net.get('h%s_%s' % (tag, cat))
                host.cmd('ping -c1 -W1 %s > /dev/null 2>&1 &' % cfg[cat]['v4gw'])
                host.cmd('ping6 -c1 -W1 %s > /dev/null 2>&1 &' % cfg[cat]['v6gw'])
    net.get('ispNode').cmd('ping -c1 -W1 %s > /dev/null 2>&1 &' % TRANSIT_V4GW)
    net.get('ispNode').cmd('sleep 5')

    # Cross-building opwarmen VANUIT gebouw B. gemeten is dat A -> B pas
    # werkt nadat B zelf verkeer heeft verstuurd.
    for tag in ('B1', 'B2', 'B3'):
        net.get('h%s_emp' % tag).cmd(
            'ping6 -c1 -W2 2001:db8:a:10::11 > /dev/null 2>&1 &')
        net.get('h%s_mgt' % tag).cmd(
            'ping6 -c1 -W2 2001:db8:a:30::11 > /dev/null 2>&1 &')
    net.get('ispNode').cmd('sleep 5')

    info("\n*** Netwerk is opgewarmd, klaar om te gaan.\n")
    info("*** Uitgaand:  hA1_emp ping -c3 203.0.113.50\n")
    info("***            hA1_emp ping6 -c3 2001:db8:ff::50\n")
    info("*** Inkomend:  netA ping -c3 10.10.0.11        (moet FALEN)\n")
    info("***            netB ping6 -c3 2001:db8:a:10::11 (moet FALEN)\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()