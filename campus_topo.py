"""
Campus SDN Topologie - Gebouw A & B (fase 2, per-gebouw gesegmenteerd)

Elk gebouw heeft eigen VLAN's, eigen subnetten en een eigen ISP-uplink:
  Gebouw A -> ISP A: 10.x + 2001:db8:a::/48, uplink op sA_core poort 4
  Gebouw B -> ISP B: 10.x + 2001:db8:b::/48, uplink op sB_core poort 5

Routing gebeurt ALLEEN tussen VLAN's die elkaar mogen bereiken (zie de
routers-sectie in faucet.yaml). Guest heeft alleen een pad naar de eigen
wan; er bestaat geen route naar employee of management.

Stateful firewall staat op de uplink-nodes (iptables/ip6tables + conntrack).
Niet in de switchpipeline: verkeer dat via een stack-poort binnenkomt slaat
de ACL-tabel over, waardoor uitgaande verbindingen niet gecommit kunnen
worden en het retourverkeer als ongevraagd zou worden gedropt.

LET OP: beide uplink-nodes draaien met inNamespace=False in de
root-namespace van de VM. Ze delen dus dezelfde kernel, routetabel en
iptables. In een echt netwerk zijn dit twee losse apparaten; hier is het
een simulatie-artefact. De firewallregels zijn source-based, zodat het
onderscheid per gebouw in de regels wel behouden blijft.
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

# ---------------------------------------------------------------------
# Adresplan. Per gebouw een eigen prefix; het derde veld in IPv6 komt
# overeen met de VLAN-categorie (10=employee, 20=guest, 30=management).
# ---------------------------------------------------------------------
BUILDINGS = {
    'A': {
        'floors': [('A1', 11), ('A2', 12)],
        'emp': {'v4': '10.10.0.%d/24', 'v4gw': '10.10.0.1',
                'v6': '2001:db8:a:10::%d/64', 'v6gw': '2001:db8:a:10::1'},
        'gst': {'v4': '10.20.0.%d/24', 'v4gw': '10.20.0.1',
                'v6': '2001:db8:a:20::%d/64', 'v6gw': '2001:db8:a:20::1'},
        'mgt': {'v4': '10.30.0.%d/26', 'v4gw': '10.30.0.1',
                'v6': '2001:db8:a:30::%d/64', 'v6gw': '2001:db8:a:30::1'},
        'v4_subnets': ('10.10.0.0/24', '10.20.0.0/24', '10.30.0.0/26'),
        'v6_subnets': ('2001:db8:a:10::/64', '2001:db8:a:20::/64',
                       '2001:db8:a:30::/64'),
        'transit_v4': '10.99.0.10/24', 'transit_v4gw': '10.99.0.1',
        'transit_v6': '2001:db8:a:99::10/64', 'transit_v6gw': '2001:db8:a:99::1',
        'internet_v6': '2001:db8:a:ff::1/128',
    },
    'B': {
        'floors': [('B1', 13), ('B2', 14), ('B3', 15)],
        'emp': {'v4': '10.11.0.%d/24', 'v4gw': '10.11.0.1',
                'v6': '2001:db8:b:10::%d/64', 'v6gw': '2001:db8:b:10::1'},
        'gst': {'v4': '10.21.0.%d/24', 'v4gw': '10.21.0.1',
                'v6': '2001:db8:b:20::%d/64', 'v6gw': '2001:db8:b:20::1'},
        'mgt': {'v4': '10.31.0.%d/26', 'v4gw': '10.31.0.1',
                'v6': '2001:db8:b:30::%d/64', 'v6gw': '2001:db8:b:30::1'},
        'v4_subnets': ('10.11.0.0/24', '10.21.0.0/24', '10.31.0.0/26'),
        'v6_subnets': ('2001:db8:b:10::/64', '2001:db8:b:20::/64',
                       '2001:db8:b:30::/64'),
        'transit_v4': '10.98.0.10/24', 'transit_v4gw': '10.98.0.1',
        'transit_v6': '2001:db8:b:99::10/64', 'transit_v6gw': '2001:db8:b:99::1',
        'internet_v6': '2001:db8:b:ff::1/128',
    },
}


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

        # === Uplinks: een ISP-node per gebouw ===
        # inNamespace=False -> root-namespace van de VM, ziet de echte eth0.
        # Alleen zo komt IPv4-verkeer op echt internet.
        ispA = self.addNode('ispA', cls=NAT, ip=BUILDINGS['A']['transit_v4'],
                            subnet='10.0.0.0/8', inNamespace=False)
        ispB = self.addNode('ispB', cls=NAT, ip=BUILDINGS['B']['transit_v4'],
                            subnet='10.0.0.0/8', inNamespace=False)

        # === Stack-links ===
        # Poortnummers EXPLICIET: Mininet nummert anders op volgorde van
        # aanmaken, en dan loopt de nummering uit de pas met faucet.yaml.
        self.addLink(sA1, sA_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sA2, sA_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB1, sB_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sB2, sB_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB3, sB_core, port1=1, port2=3, cls=TCLink, bw=1000)

        # Darkfiber: sA_core p3 <-> sB_core p4
        self.addLink(sA_core, sB_core, port1=3, port2=4,
                     cls=TCLink, bw=1000, delay='5ms')

        # Uplinks
        self.addLink(ispA, sA_core, port2=4)
        self.addLink(ispB, sB_core, port2=5)

        # === Hosts: per verdieping employee / guest / management ===
        switches = {'A1': sA1, 'A2': sA2, 'B1': sB1, 'B2': sB2, 'B3': sB3}
        for bld, cfg in BUILDINGS.items():
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


def configure_uplink(node, cfg, name):
    """
    Uplink-node: NAT voor IPv4, routing voor IPv6, stateful firewall voor beide.

    De conntrack-module in de kernel houdt bij welke verbindingen lopen.
    ESTABLISHED/RELATED = antwoord op iets van binnenuit  -> door
    NEW vanaf de campus                                   -> door (en onthouden)
    Al het overige inkomend verkeer                       -> weg
    """
    info("*** Uplink %s configureren...\n" % name)
    node.cmd('sysctl -w net.ipv4.ip_forward=1')
    node.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')

    iface = '%s-eth0' % name
    node.cmd('ip -6 addr add %s dev %s' % (cfg['transit_v6'], iface))
    # Gesimuleerd "internet" achter deze ISP. VirtualBox heeft geen
    # IPv6-uplink, dus dit is het adres waar campus-hosts naartoe pingen.
    node.cmd('ip -6 addr add %s dev lo' % cfg['internet_v6'])

    # --- IPv4: NAT naar echt internet ---
    # Per gebouw een eigen source-based MASQUERADE. De -C check voorkomt
    # dubbele regels bij herstart (root-namespace wordt niet opgeruimd).
    for subnet in cfg['v4_subnets']:
        rule = '-t nat POSTROUTING -s %s ! -d 10.0.0.0/8 -j MASQUERADE' % subnet
        node.cmd('iptables -C %s 2>/dev/null || iptables -A %s' % (rule, rule))

    # --- Stateful firewall IPv4 ---
    for subnet in cfg['v4_subnets']:
        node.cmd('iptables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                 % subnet)

    # --- Stateful firewall IPv6 ---
    # Bij IPv6 is er geen NAT. Deze firewall is dus de ENIGE bescherming
    # tegen ongevraagd inkomend verkeer; elke host is anders direct
    # vanaf het internet bereikbaar.
    for subnet in cfg['v6_subnets']:
        node.cmd('ip6tables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                 % subnet)

    # --- Retourroutes naar de interne VLAN's via de Faucet-VIP ---
    for subnet in cfg['v4_subnets']:
        node.cmd('ip route replace %s via %s' % (subnet, cfg['transit_v4gw']))
    for subnet in cfg['v6_subnets']:
        node.cmd('ip -6 route replace %s via %s' % (subnet, cfg['transit_v6gw']))


#def setup_firewall_base():
    """
    Basisregels van de firewall. Deze staan in de root-namespace en gelden
    dus voor beide uplink-nodes samen - vandaar dat ze eenmalig gezet
    worden, voordat de per-gebouw ACCEPT-regels eraan toegevoegd worden.
    """
#    import subprocess
#    for cmd in (
        # Schone lei
#        'iptables -F FORWARD', 'ip6tables -F FORWARD',
        # Default policy: alles weigeren wat niet expliciet is toegestaan
#        'iptables -P FORWARD DROP', 'ip6tables -P FORWARD DROP',
        # Antwoordverkeer op iets van binnenuit mag terug
#        'iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
#        'ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
        # Onzinnige pakketten meteen weg
#        'iptables -A FORWARD -m conntrack --ctstate INVALID -j DROP',
#        'ip6tables -A FORWARD -m conntrack --ctstate INVALID -j DROP',
        # Neighbor Discovery moet altijd door, anders breekt IPv6 volledig
#        'ip6tables -A FORWARD -p icmpv6 --icmpv6-type 133 -j ACCEPT',
#        'ip6tables -A FORWARD -p icmpv6 --icmpv6-type 134 -j ACCEPT',
#        'ip6tables -A FORWARD -p icmpv6 --icmpv6-type 135 -j ACCEPT',
#        'ip6tables -A FORWARD -p icmpv6 --icmpv6-type 136 -j ACCEPT',
#    ):
#        subprocess.call(['sudo'] + cmd.split())


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

    info("*** Firewall-basis instellen (root-namespace, geldt voor beide uplinks)...\n")
    setup_firewall_base()

    configure_uplink(net.get('ispA'), BUILDINGS['A'], 'ispA')
    configure_uplink(net.get('ispB'), BUILDINGS['B'], 'ispB')

    info("\n*** Klaar. Geef de stack 30-60s om te convergeren.\n")
    info("*** IPv4 A:   hA1_emp ping -c2 8.8.8.8\n")
    info("*** IPv6 A:   hA1_emp ping6 -c3 2001:db8:a:ff::1\n")
    info("*** IPv6 B:   hB1_emp ping6 -c3 2001:db8:b:ff::1\n")
    info("*** Cross:    hA1_emp ping -c2 10.11.0.13   (employee A -> B)\n")
    info("*** Firewall: ispA ping6 -c2 2001:db8:a:10::11   (moet FALEN)\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()