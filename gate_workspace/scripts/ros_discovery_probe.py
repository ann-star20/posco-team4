"""Isolated ROS data-path probe; does not touch application DB or existing nodes."""
import argparse
import json
import os
import subprocess
import sys
import time

NODE = r'''
import sys,time,rclpy
from rclpy.node import Node
from std_msgs.msg import String
rclpy.init(); n=Node('fab_probe_'+sys.argv[1]); started=time.monotonic()
if sys.argv[1]=='subscriber':
    done=False
    def receive(message):
        global done
        done=True
        print('received',flush=True)
    sub=n.create_subscription(String,'/fab_probe_only',receive,10)
    while not done and time.monotonic()-started<12:rclpy.spin_once(n,timeout_sec=.05)
else:
    pub=n.create_publisher(String,'/fab_probe_only',10)
    while not pub.get_subscription_count() and time.monotonic()-started<8:rclpy.spin_once(n,timeout_sec=.05)
    print('discovery',round(time.monotonic()-started,3),'subscribers',pub.get_subscription_count(),flush=True)
    for _ in range(10):
        message=String();message.data='probe';pub.publish(message);time.sleep(.1)
n.destroy_node();rclpy.shutdown()
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--domain',default='91')
    parser.add_argument('--server-port',type=int,default=11841)
    parser.add_argument('--simple',action='store_true')
    parser.add_argument('--profile')
    parser.add_argument('--localhost-only',action='store_true')
    args=parser.parse_args()
    env=os.environ.copy();env['ROS_DOMAIN_ID']=args.domain
    env['ROS_DISCOVERY_SERVER']=f'127.0.0.1:{args.server_port}';env['ROS_LOCALHOST_ONLY']='0'
    if args.localhost_only:env['ROS_LOCALHOST_ONLY']='1'
    env.pop('FASTRTPS_DEFAULT_PROFILES_FILE',None);env.pop('FASTDDS_DEFAULT_PROFILES_FILE',None)
    if args.profile:env['FASTRTPS_DEFAULT_PROFILES_FILE']=args.profile
    server=None
    if args.simple:env.pop('ROS_DISCOVERY_SERVER',None)
    else:
        server=subprocess.Popen(['bash','/opt/ros/humble/bin/fastdds','discovery','-i','0','-l','127.0.0.1','-p',str(args.server_port)],
                                env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    sub=None
    try:
        time.sleep(.5)
        if server and server.poll() is not None:raise RuntimeError('discovery server failed to start')
        sub=subprocess.Popen([sys.executable,'-u','-c',NODE,'subscriber'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        time.sleep(.5)
        pub=subprocess.run([sys.executable,'-u','-c',NODE,'publisher'],env=env,capture_output=True,text=True,timeout=12)
        output,error=sub.communicate(timeout=5)
        okay='received' in output and pub.returncode==0 and sub.returncode==0
        print(json.dumps({'success':okay,'publisher':pub.stdout.strip(),'subscriber':output.strip(),
                          'errors':pub.stderr+error}))
        return 0 if okay else 1
    finally:
        if sub and sub.poll() is None:sub.terminate();sub.wait(timeout=3)
        if server:server.terminate();server.wait(timeout=3)

if __name__=='__main__':raise SystemExit(main())
