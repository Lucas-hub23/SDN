"""
Campus SDN Topologie - Gebouw A & B (fase 2, per-gebouw gesegmenteerd)

User-VLAN's per gebouw, met een eigen /48 per gebouw:
  Gebouw A -> 10.10/10.20/10.30 + 2001:db8:a::/48
  Gebouw B -> 10.11/10.21/10.31 + 2001:db8:b::/48

Twee uplinks in EEN gedeeld transit-VLAN (10.99.0.0/24 + 2001:db8:99::/64):
  natNode  op sA_core p4 - IPv4 NAT naar echt internet (root-namespace)
  ispNode  op sB_core p5 - IPv6 routing naar gesimuleerde ISP (eigen namespace)

Het transit-VLAN is gedeeld omdat beide gebouwen beide uplinks moeten kunnen
bereiken: IPv4 loopt via gebouw A, IPv6 via gebouw B, en de darkfiber verbindt
ze. Er hangen geen gebruikers in dit VLAN.

Stateful firewall staat op de uplink-nodes (iptables/ip6tables + conntrack),
niet in de switchpipeline: verkeer dat via een stack-poort binnenkomt slaat de
ACL-tabel over, waardoor uitgaande verbindingen niet gecommit kunnen worden.
De firewallblokken staan hieronder uitgecommentarieerd; zet ze aan in blok 8
van het testplan.
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

# --- Transit ---
NAT_V4 = '10.99.0.10'          # natNode, gebouw A
ISP_V4 = '10.99.0.20'          # ispNode, gebouw B
ISP_V6 = '2001:db8:99::20'
TRANSIT_V4GW = '10.99.0.1'     # Faucet-VIP op het transit-VLAN
TRANSIT_V6GW = '2001:db8:99::1'
INTERNET_V6 = '2001:db8:ff::1' # gesimuleerd "internet" achter ispNode

# --- Adresplan per gebouw ---
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

# Alle interne subnetten - voor NAT, retourroutes en firewallregels
V4_SUBNETS = ('10.10.0.0/24', '10.20.0.0/24', '10.30.0.0/26',
              '10.11.0.0/24', '10.21.0.0/24', '10.31.0.0/26')
V6_SUBNETS = ('2001:db8:a:10::/64', '2001:db8:a:20::/64', '2001:db8:a:30::/64',
              '2001:db8:b:10::/64', '2001:db8:b:20::/64', '2001:db8:b:30::/64')


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

        # === Uplink gebouw A: NAT-node voor IPv4 ===
        # inNamespace=False -> deelt de root-namespace van de VM en ziet
        # daardoor de echte eth0. Alleen zo kom je op echt internet.
        nat = self.addNode('natNode', cls=NAT, ip='%s/24' % NAT_V4,
                           subnet='10.0.0.0/8', inNamespace=False)

        # === Uplink gebouw B: ISP-node voor IPv6 ===
        # Gewone host in een EIGEN namespace: eigen routetabel en eigen
        # ip6tables, los van de VM. Simuleert de router van de provider.
        isp = self.addHost('ispNode', ip='%s/24' % ISP_V4)

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
        self.addLink(nat, sA_core, port2=4)
        self.addLink(isp, sB_core, port2=5)

        # === Hosts: per verdieping employee / guest / management ===
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
    "natNode: IPv4 NAT naar echt internet. Draait in de root-namespace."
    info("*** natNode configureren (IPv4 uplink gebouw A)...\n")
    nat = net.get('natNode')
    nat.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Mininet's NAT-klasse zet zelf FORWARD op DROP. Zolang de stateful
    # firewall uit staat, moet die policy terug op ACCEPT - anders wordt
    # al het doorgestuurde verkeer weggegooid.
    # LET OP: dit past de FORWARD-chain van de HELE VM aan.
    nat.cmd('iptables -P FORWARD ACCEPT')

    # Interface-onafhankelijke MASQUERADE per subnet. De -C check voorkomt
    # dubbele regels bij herstart: de root-namespace wordt niet opgeruimd
    # door net.stop().
    for subnet in V4_SUBNETS:
        rule = '-t nat POSTROUTING -s %s ! -d 10.0.0.0/8 -j MASQUERADE' % subnet
        nat.cmd('iptables -C %s 2>/dev/null || iptables -A %s' % (rule, rule))

    # Retourroutes naar de interne VLAN's via de Faucet-VIP op het transit-VLAN
    for subnet in V4_SUBNETS:
        nat.cmd('ip route replace %s via %s' % (subnet, TRANSIT_V4GW))

    # --- Stateful firewall IPv4 (blok 8 van het testplan) ---
    # Bij IPv4 doet NAT al impliciet iets vergelijkbaars: zonder vertaling
    # komt ongevraagd inkomend verkeer nergens. Deze regels maken dat
    # expliciet en controleerbaar.
    #
    # nat.cmd('iptables -F FORWARD')
    # nat.cmd('iptables -P FORWARD DROP')
    # nat.cmd('iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    # nat.cmd('iptables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    # for subnet in V4_SUBNETS:
    #     nat.cmd('iptables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
    #             % subnet)


def configure_isp(net):
    "ispNode: IPv6 routing naar de gesimuleerde ISP. Eigen namespace."
    info("*** ispNode configureren (IPv6 uplink gebouw B)...\n")
    isp = net.get('ispNode')
    isp.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    isp.cmd('sysctl -w net.ipv4.ip_forward=1')

    isp.cmd('ip -6 addr add %s/64 dev ispNode-eth0' % ISP_V6)
    # "Een host op internet". VirtualBox heeft geen IPv6-uplink (aantoonbaar
    # met ping6 naar 2001:4860:4860::8888), dus de ISP wordt gesimuleerd.
    isp.cmd('ip -6 addr add %s/128 dev lo' % INTERNET_V6)

    # Retourroutes naar de interne VLAN's via de Faucet-VIP
    for subnet in V6_SUBNETS:
        isp.cmd('ip -6 route replace %s via %s' % (subnet, TRANSIT_V6GW))

    # --- Stateful firewall IPv6 (blok 8 van het testplan) ---
    # Bij IPv6 is er GEEN NAT. Deze firewall is de enige bescherming tegen
    # ongevraagd inkomend verkeer; elke host is anders direct vanaf het
    # internet bereikbaar. Deze regels raken alleen de namespace van
    # ispNode, niet de VM.
    #
    # isp.cmd('ip6tables -P FORWARD DROP')
    # isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    # isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    # # Neighbor Discovery moet altijd door, anders breekt IPv6 volledig
    # for icmp6 in ('133', '134', '135', '136'):
    #     isp.cmd('ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -j ACCEPT' % icmp6)
    # for subnet in V6_SUBNETS:
    #     isp.cmd('ip6tables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
    #             % subnet)


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

    info("\n*** Klaar. Geef de stack 30-60s om te convergeren.\n")
    info("*** IPv4:     hA1_emp ping -c2 8.8.8.8\n")
    info("*** IPv6:     hA1_emp ping6 -c3 2001:db8:ff::1\n")
    info("*** Cross:    hA1_emp ping -c3 10.11.0.13   (employee A -> B)\n")
    info("*** Blokkade: hA1_emp ping -c2 10.30.0.11   (moet FALEN)\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()