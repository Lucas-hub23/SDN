"""
Campus SDN Topologie voor gebouw A & B met 3/4 VLANS(stabiele versie, dual-stack)
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

NAT_V4 = '10.99.0.10'
ISP_V4 = '10.99.0.20'
ISP_V6 = '2001:db8:99::20'
TRANSIT_V4GW = '10.99.0.1'
TRANSIT_V6GW = '2001:db8:99::1'
INTERNET_V6 = '2001:db8:ff::1'

FLOORS = [('A1', 11), ('A2', 12), ('B1', 13), ('B2', 14), ('B3', 15)]

CATEGORIES = {
    'emp': {'v4': '10.10.0.%d/23', 'v4gw': '10.10.0.1',
            'v6': '2001:db8:10::%d/64', 'v6gw': '2001:db8:10::1'},
    'gst': {'v4': '10.20.0.%d/24', 'v4gw': '10.20.0.1',
            'v6': '2001:db8:20::%d/64', 'v6gw': '2001:db8:20::1'},
    'mgt': {'v4': '10.30.0.%d/26', 'v4gw': '10.30.0.1',
            'v6': '2001:db8:30::%d/64', 'v6gw': '2001:db8:30::1'},
}

V4_SUBNETS = ('10.10.0.0/23', '10.20.0.0/24', '10.30.0.0/26')
V6_SUBNETS = ('2001:db8:10::/64', '2001:db8:20::/64', '2001:db8:30::/64')


class CampusTopo(Topo):
    def build(self):
        sA_core = self.addSwitch('sA_core', dpid='0000000000000001')
        sA1 = self.addSwitch('sA1', dpid='0000000000000002')
        sA2 = self.addSwitch('sA2', dpid='0000000000000003')
        sB_core = self.addSwitch('sB_core', dpid='0000000000000004')
        sB1 = self.addSwitch('sB1', dpid='0000000000000005')
        sB2 = self.addSwitch('sB2', dpid='0000000000000006')
        sB3 = self.addSwitch('sB3', dpid='0000000000000007')

        nat = self.addNode('natNode', cls=NAT, ip='%s/24' % NAT_V4,
                           subnet='10.0.0.0/8', inNamespace=False)

        isp = self.addHost('ispNode', ip='%s/24' % ISP_V4)

        self.addLink(sA1, sA_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sA2, sA_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB1, sB_core, port1=1, port2=1, cls=TCLink, bw=1000)
        self.addLink(sB2, sB_core, port1=1, port2=2, cls=TCLink, bw=1000)
        self.addLink(sB3, sB_core, port1=1, port2=3, cls=TCLink, bw=1000)

        self.addLink(sA_core, sB_core, port1=3, port2=4,
                     cls=TCLink, bw=1000, delay='5ms')

        self.addLink(nat, sA_core, port2=4)
        self.addLink(isp, sB_core, port2=5)

        switches = {'A1': sA1, 'A2': sA2, 'B1': sB1, 'B2': sB2, 'B3': sB3}
        for tag, n in FLOORS:
            sw = switches[tag]
            for i, cat in enumerate(('emp', 'gst', 'mgt')):
                host = self.addHost('h%s_%s' % (tag, cat),
                                    ip=CATEGORIES[cat]['v4'] % n)
                self.addLink(host, sw, port2=2 + i)


def configure_hosts(net):
    "Dual-stack adressen en default gateways per host"
    info("\n*** Hosts configureren (dual-stack)...\n")
    for tag, n in FLOORS:
        for cat in ('emp', 'gst', 'mgt'):
            host = net.get('h%s_%s' % (tag, cat))
            iface = '%s-eth0' % host.name
            cfg = CATEGORIES[cat]
            host.cmd('ip route replace default via %s' % cfg['v4gw'])
            host.cmd('ip -6 addr add %s dev %s' % (cfg['v6'] % n, iface))
            host.cmd('ip -6 route replace default via %s' % cfg['v6gw'])


def configure_nat(net):
    """
    natNode: IPv4 NAT + stateful firewall. Draait in de root-namespace.

    De conntrack-module in de kernel houdt bij welke verbindingen lopen:
      ESTABLISHED/RELATED = antwoord op iets van binnenuit  -> door
      NEW vanaf de campus                                   -> door (onthouden)
      Al het overige inkomend verkeer                       -> weg
    """
    info("*** natNode configureren (IPv4 uplink gebouw A + firewall)...\n")
    nat = net.get('natNode')
    nat.cmd('sysctl -w net.ipv4.ip_forward=1')

    rule = '-t nat POSTROUTING -s 10.0.0.0/8 ! -d 10.0.0.0/8 -j MASQUERADE'
    nat.cmd('iptables -C %s 2>/dev/null || iptables -A %s' % (rule, rule))

    nat.cmd('iptables -F FORWARD')
    nat.cmd('iptables -P FORWARD DROP')
    nat.cmd('iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    nat.cmd('iptables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    for subnet in V4_SUBNETS:
        nat.cmd('iptables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                % subnet)

    for subnet in V4_SUBNETS:
        nat.cmd('ip route replace %s via %s' % (subnet, TRANSIT_V4GW))


def configure_isp(net):
    """
    ispNode: IPv6 routing naar de gesimuleerde ISP + stateful firewall.
    Eigen namespace, dus deze regels raken de VM niet.

    Bij IPv6 is er GEEN NAT. Deze firewall is de enige bescherming tegen
    ongevraagd inkomend verkeer; zonder firewall is elke campus-host
    direct vanaf het internet bereikbaar.
    """
    info("*** ispNode configureren (IPv6 uplink gebouw B + firewall)...\n")
    isp = net.get('ispNode')
    isp.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    isp.cmd('sysctl -w net.ipv4.ip_forward=1')

    isp.cmd('ip -6 addr add %s/64 dev ispNode-eth0' % ISP_V6)
    isp.cmd('ip -6 addr add %s/128 dev ispNode-eth0' % INTERNET_V6)

    isp.cmd('ip6tables -F FORWARD')
    isp.cmd('ip6tables -P FORWARD DROP')
    isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    isp.cmd('ip6tables -A FORWARD -m conntrack --ctstate INVALID -j DROP')
    for icmp6 in ('133', '134', '135', '136'):
        isp.cmd('ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -j ACCEPT' % icmp6)
    for subnet in V6_SUBNETS:
        isp.cmd('ip6tables -A FORWARD -s %s -m conntrack --ctstate NEW -j ACCEPT'
                % subnet)

    for subnet in V6_SUBNETS:
        isp.cmd('ip -6 route replace %s via %s' % (subnet, TRANSIT_V6GW))


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
    info("*** IPv4:     hA1_emp ping -c3 8.8.8.8\n")
    info("*** IPv6:     hA1_emp ping6 -c3 2001:db8:ff::1\n")
    info("*** Darkfiber: hA1_emp ping -c3 10.10.0.15\n")
    info("*** Blokkade: hA1_emp ping -c2 10.30.0.11   (moet FALEN)\n")
    info("*** Firewall: ispNode ping6 -c2 2001:db8:10::11   (moet FALEN)\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()