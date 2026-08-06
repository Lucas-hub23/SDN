"""
Campus SDN Topologie - Gebouw A & B
Employee 10.10.0.0/23 | Guest 10.20.0.0/24 | Mgmt 10.30.0.0/26 | Transit 10.99.0.0/24
Routing via Faucet (inter-VLAN), internet via NAT-node in root-namespace.
Switch-onderlinge links zijn stack-links (zie faucet.yaml).
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

        # NAT-node op sA_core p4 (native_vlan wan)
        self.addLink(nat, sA_core, port2=4)

        # === Hosts: per verdieping employee / guest / management ===
        floors = [
            ('A1', sA1, 11), ('A2', sA2, 12),
            ('B1', sB1, 13), ('B2', sB2, 14), ('B3', sB3, 15),
        ]
        for tag, sw, n in floors:
            emp = self.addHost('h%s_emp' % tag, ip='10.10.0.%d/23' % n)
            gst = self.addHost('h%s_gst' % tag, ip='10.20.0.%d/24' % n)
            mgt = self.addHost('h%s_mgt' % tag, ip='10.30.0.%d/26' % n)
            self.addLink(emp, sw, port2=2)
            self.addLink(gst, sw, port2=3)
            self.addLink(mgt, sw, port2=4)


GATEWAYS = {'emp': '10.10.0.1', 'gst': '10.20.0.1', 'mgt': '10.30.0.1'}


def run():
    net = Mininet(
        topo=CampusTopo(),
        controller=lambda name: RemoteController(name, ip=FAUCET_IP, port=6653),
        switch=partial(OVSSwitch, protocols='OpenFlow13'),
        link=TCLink,
        waitConnected=True,
    )
    net.start()

    info("\n*** Default gateways instellen per host...\n")
    for host in net.hosts:
        if host.name == 'natNode':
            continue
        gw = GATEWAYS[host.name.split('_')[1]]
        host.cmd('ip route replace default via %s' % gw)

    info("*** NAT-node configureren...\n")
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
    for subnet in ('10.10.0.0/23', '10.20.0.0/24', '10.30.0.0/26'):
        nat.cmd('ip route replace %s via 10.99.0.1' % subnet)

    info("*** Klaar. Geef de stack 30-60s om te convergeren voor je test.\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()