# Panel setup for notifications

## Galaxy Flex V3 panels

**Setup the Ethernet module under Communications[56] -> Module config [56.3] -> Ethernet[56.3.3]:**

`56.3.3.1 DHCP` - set according to your network, typically 1 = Enabled.

`56.3.3.2 IP Address` - Set static IP Address if not using DHCP.

`56.3.3.3 Gateway IP` - Set Gateway IP Address if not using DHCP, or if needed.

`56.3.3.4 Network Mask` - Set size of your network if not using DHCP. Typically 255.255.255.0 if you dont know.

`56.3.3.5 Encrypt` - `Alarm Report[1]` - set to 0 = Disabled and `IP Check[3]` to 0 = Disabled.

`56.3.3.6 Line Fail` - Enable if you want the panel to monitor the network.

`56.3.3.7 IP Check Cfg` - Set `intervals[1]` for heartbeat check if you want to use this feature (00:00 = disabled). Set `Acknowledge[2]` to Data if you want a fault if it fails.

**Setup the Notification Reciever under Communications[56] -> ARC Notify[56.1] -> Recievers[56.1.1] -> Receiver 1[56.1.1.1] -> Ethernet[56.1.1.1.4]:**

`56.1.1.1.4.1 Destination` - Point this to your SIA-Server local address. Note, use < (B) to erase, and * to place a 'dot'.

`56.1.1.1.4.2 Format` - Select SIA, after which you are asked for SIA Level, select 3.

`56.1.1.1.4.3 Autotest` - If you want a periodic test notification, set `Intervals[1]` to a time, for example 24:00 and leave `Account No.[2]` blank unless you have specific requirements.

**Setup the Notification Reports under Communications[56] -> ARC Notify[56.1] -> Reports[56.1.2] -> ARC[56.1.2.1]:**

`56.1.2.1.1 Account No` - Select an arbitrary 6 number account number used to identify this panel.

`56.1.2.1.2 Triggers` - Select the events you want notification on.

`56.1.2.1.3 Rx Sequence` - Select recievers and sequence this report should go to, if you have more than one, add them as a list. if you only have setup a single sia-server on reciever 1 then set this just to 1. if you have a backup sia-server, you could set this to 12 to use reciever 1 first and reciever 2 if nr 1 fails.

`56.1.2.1.5 IP Check (ARC Report only)` - Enable or disable the heartbeat check.
