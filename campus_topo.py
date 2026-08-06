"""
Campus SDN Topologie - Gebouw A & B (fase 2: dual-stack)
IPv4: Employee 10.10.0.0/23 | Guest 10.20.0.0/24 | Mgmt 10.30.0.0/26 | Transit 10.99.0.0/24
IPv6: Employee 2001:db8:10::/64 | Guest 2001:db8:20::/64 | Mgmt 2001:db8:30::/64
      Transit 2001:db8:99::/64  | "Internet" achter ISP-node: 2001:db8:ff::1

IPv4 gaat via de NAT-node naar echt internet (MASQUERADE).
IPv6 gaat via de ISP-node - VirtualBox' NAT-engine heeft geen IPv6-uplink,
dus de ISP wordt gesimuleerd. Geen NAT nodig: IPv6 is end-to-end routeerbaar.
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

# Verdiepingen: (tag, host-nummer). Het nummer is het laatste octet in v4
# en het laatste veld in v6, zodat adressen makkelijk te herleiden zijn.
FLOORS = [('A1', 11), ('A2', 12), ('B1', 13), ('B2', 14), ('B3', 15)]

# Per categorie: adresformaat en gateway, voor beide protocollen
CATEGORIES = {
    'emp': {'v4': '10.10.0.%d/23',  'v4gw': '10.10.0.1',
            'v6': '2001:db8:10::%d/64', 'v6gw': '2001:db8:10::1'},
    'gst': {'v4': '10.20.0.%d/24',  'v4gw': '10.20.0.1',
            'v6': '2001:db8:20::%d/64', 'v6gw': '2001:db8:20::1'},
    'mgt': {'v4': '10.30.0.%d/26',  'v4gw': '10.30.0.1',
            'v6': '2001:db8:30::%d/64', 'v6gw': '2001:db8:30::1'},
}

# Interne subnetten - nodig voor de retourroutes op NAT- en ISP-node
V4_SUBNETS = ('10.10.0.0/23', '10.20.0.0/24', '10.30.0.0/26')
V6_SUBNETS = ('2001:db8:10::/64', '2001:db8:20::/64', '2001:db8:30::/64')


class CampusTopo(Topo):
    def build(self):
        # === Switches ===
        sA_core = self.addSwitch('sA_core', dpid='0000000000000001')
        sA1 = self.addSwitch('sA1', dpid='0000000000000002')
        sA2 = self.addSwitch('sA2', dpid='0000000000000003')
        sB_core = self.addSwitch('sB_core', dpid='0000000000000004')
        sB1 = self.addSwitch('sB1', dpid='0000000000000005')
        sB2 = self.addSwitch('sB2', dpid='0000000000000006')
        sB3 = self.addSwitch('sB3', dpid='0000000000000007')

        # === NAT-node (root-namespace, ziet echt eth0 van de VM) ===
        nat = self.addNode('natNode', cls=NAT, ip='10.99.0.10/24',
                           subnet='10.0.0.0/8', inNamespace=False)

        # === ISP-node: simuleert de router van de provider (IPv6) ===
        # Gewone host in eigen namespace; krijgt in run() een extra adres
        # 2001:db8:ff::1 dat "een host op internet" voorstelt.
        isp = self.addHost('ispNode', ip='10.99.0.20/24')

        # === Stack-links ===
        # Poortnummers EXPLICIET: Mininet nummert anders op volgorde van
        # aanmaken, en dan loopt de nummering uit de pas met faucet.yaml.
        self.addLink(sA1, sA_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sA2, sA_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB1, sB_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sB2, sB_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB3, sB_core, port1=1, port2=3, cls=TCLink, bw=1000)

        # Darkfiber tussen de gebouwen: sA_core p3 <-> sB_core p4
        self.addLink(sA_core, sB_core, port1=3, port2=4,
                     cls=TCLink, bw=1000, delay='5ms')

        # Transit-poorten op sA_core (beide native_vlan wan)
        self.addLink(nat, sA_core, port2=4)    # NAT-node  -> IPv4 uplink
        self.addLink(isp, sA_core, port2=5)    # ISP-node  -> IPv6 uplink

        # === Hosts: per verdieping employee / guest / management ===
        switches = {'A1': sA1, 'A2': sA2, 'B1': sB1, 'B2': sB2, 'B3': sB3}
        for tag, n in FLOORS:
            sw = switches[tag]
            for i, cat in enumerate(('emp', 'gst', 'mgt')):
                host = self.addHost('h%s_%s' % (tag, cat),
                                    ip=CATEGORIES[cat]['v4'] % n)
                self.addLink(host, sw, port2=2 + i)   # emp=2, gst=3, mgt=4


def run():
    net = Mininet(
        topo=CampusTopo(),
        controller=lambda name: RemoteController(name, ip=FAUCET_IP, port=6653),
        switch=partial(OVSSwitch, protocols='OpenFlow13'),
        link=TCLink,
        waitConnected=True,
    )
    net.start()

    info("\n*** Hosts configureren (IPv4 gateway + IPv6 adres/gateway)...\n")
    for tag, n in FLOORS:
        for cat in ('emp', 'gst', 'mgt'):
            host = net.get('h%s_%s' % (tag, cat))
            iface = '%s-eth0' % host.name
            cfg = CATEGORIES[cat]
            # IPv4 default gateway (adres is al gezet via addHost)
            host.cmd('ip route replace default via %s' % cfg['v4gw'])
            # IPv6 adres + default gateway
            host.cmd('ip -6 addr add %s dev %s' % (cfg['v6'] % n, iface))
            host.cmd('ip -6 route replace default via %s' % cfg['v6gw'])

    info("*** NAT-node configureren (IPv4 uplink naar echt internet)...\n")
    nat = net.get('natNode')
    nat.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Interface-onafhankelijke MASQUERADE.
    # Eerst -C (check): bestaat de regel al, dan slaan we -A over.
    # Zonder deze check krijg je een dubbele regel bij elke herstart,
    # want de root-namespace wordt niet opgeruimd door net.stop().
    check = 'iptables -t nat -C POSTROUTING -s 10.0.0.0/8 ! -d 10.0.0.0/8 -j MASQUERADE'
    add = 'iptables -t nat -A POSTROUTING -s 10.0.0.0/8 ! -d 10.0.0.0/8 -j MASQUERADE'
    nat.cmd('%s 2>/dev/null || %s' % (check, add))

    # Let op: past de FORWARD-policy van de HELE VM aan (nodig als Docker draait)
    nat.cmd('iptables -P FORWARD ACCEPT')

    # Retourroutes naar de interne VLAN's via de Faucet-VIP op het transit-VLAN
    for subnet in V4_SUBNETS:
        nat.cmd('ip route replace %s via 10.99.0.1' % subnet)

    info("*** ISP-node configureren (IPv6 uplink, gesimuleerd)...\n")
    isp = net.get('ispNode')
    isp.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    isp.cmd('sysctl -w net.ipv4.ip_forward=1')
    # Adres op het transit-VLAN
    isp.cmd('ip -6 addr add 2001:db8:99::20/64 dev ispNode-eth0')
    # "Een host op internet" - hier pingen de campus-hosts straks naartoe
    isp.cmd('ip -6 addr add 2001:db8:ff::1/128 dev lo')
    # Retourroutes naar de interne VLAN's via de Faucet-VIP
    for subnet in V6_SUBNETS:
        isp.cmd('ip -6 route replace %s via 2001:db8:99::1' % subnet)

    info("\n*** Klaar. Geef de stack 30-60s om te convergeren.\n")
    info("*** IPv4 test:  hA1_emp ping -c2 8.8.8.8\n")
    info("*** IPv6 test:  hA1_emp ping6 -c2 2001:db8:ff::1\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()