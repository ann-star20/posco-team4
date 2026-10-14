from setuptools import find_packages, setup

setup(
    name="fab_virtual_lot",
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/fab_virtual_lot"]),
        ("share/fab_virtual_lot", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="POSCO virtual fab team",
    maintainer_email="team@example.invalid",
    description="Virtual fab ROS 2 publisher",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "fab_demo_publisher = fab_virtual_lot.publisher:main",
        "fab_command_subscriber = fab_virtual_lot.command_subscriber:main",
    ]},
)
