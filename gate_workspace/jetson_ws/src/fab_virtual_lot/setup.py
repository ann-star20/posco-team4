from setuptools import find_packages, setup

setup(
    name="fab_virtual_lot",
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/fab_virtual_lot"]),
        ("share/fab_virtual_lot", ["package.xml"]),
    ],
    install_requires=["setuptools", "httpx>=0.27,<1", "websockets>=13,<16"],
    zip_safe=True,
    maintainer="POSCO virtual fab team",
    maintainer_email="team@example.invalid",
    description="Virtual fab ROS 2 publisher",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "fab_demo_publisher = fab_virtual_lot.publisher:main",
        "fab_command_subscriber = fab_virtual_lot.command_subscriber:main",
        "fab_aoi_worker = fab_virtual_lot.aoi_worker:main",
        "fab_aoi_request = fab_virtual_lot.aoi_request:main",
        "fab_surrogate_worker = fab_virtual_lot.surrogate_worker:main",
        "fab_diagnosis_worker = fab_virtual_lot.diagnosis_worker:main",
        "fab_aoi_unity_server = fab_virtual_lot.aoi_unity:main",
    ]},
)
