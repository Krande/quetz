import json

import pytest

from quetz.db_models import PackageVersion
from quetz.pkgstores import PackageStore
from quetz.rest_models import Channel
from quetz.tasks.indexing import validate_packages
from quetz.tasks.reindexing import reindex_packages_from_store, reindex_all_packages_from_store, check_doorstep


@pytest.fixture
def pkgstore(config):
    pkgstore = config.get_package_store()
    return pkgstore


@pytest.fixture
def package_filenames():
    return ["test-package-0.1-0.tar.bz2", "test-package-0.2-0.tar.bz2"]


@pytest.fixture
def package_files(pkgstore: PackageStore, channel_name, package_filenames):
    pkgstore.create_channel(channel_name)
    for filename in package_filenames:
        with open(filename, "rb") as fid:
            content = fid.read()
        pkgstore.add_file(content, channel_name, f"linux-64/{filename}")


@pytest.fixture
def channel(dao, user, channel_name):
    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")

    return channel


@pytest.fixture
def remove_package_versions(db):
    # clean up the created package versions after the test

    yield

    db.query(PackageVersion).delete()
    db.commit()


def test_reindex_package_files(
    config,
    user,
    package_files,
    channel,
    db,
    dao,
    pkgstore: PackageStore,
    package_filenames,
    remove_package_versions,
):
    user_id = user.id
    reindex_packages_from_store(dao, config, channel.name, user_id)
    db.refresh(channel)

    assert channel.packages
    assert channel.packages[0].name == "test-package"
    assert channel.packages[0].members[0].user.username == user.username
    assert (
        channel.packages[0].package_versions[0].version == "0.1"
        or channel.packages[0].package_versions[0].version == "0.2"
    )
    assert (
        channel.packages[0].package_versions[1].version == "0.1"
        or channel.packages[0].package_versions[1].version == "0.2"
    )

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata["packages"]) == 2
    assert set(repodata["packages"].keys()) == set(package_filenames)

def test_reindex_all_package_files(
    config,
    user,
    package_files,
    db,
    dao,
    pkgstore: PackageStore,
    package_filenames,
    remove_package_versions,
):
    user_id = user.id
    channels = reindex_all_packages_from_store(dao, config, user_id)

    channel = channels[0]

    assert channel.packages
    assert channel.packages[0].name == "test-package"
    assert channel.packages[0].members[0].user.username == user.username
    assert (
        channel.packages[0].package_versions[0].version == "0.1"
        or channel.packages[0].package_versions[0].version == "0.2"
    )
    assert (
        channel.packages[0].package_versions[1].version == "0.1"
        or channel.packages[0].package_versions[1].version == "0.2"
    )

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata["packages"]) == 2
    assert set(repodata["packages"].keys()) == set(package_filenames)

def test_check_doorstep(
    config,
    user,
    package_files,
    db,
    dao,
    channel,
    pkgstore: PackageStore,
    package_filenames,
    remove_package_versions,
):

    user_id = user.id

    reindex_all_packages_from_store(dao, config, user_id)
    packages_before = channel.packages

    packages = check_doorstep(dao, config, user_id)
    assert len(packages) == 1

    packages_after = channel.packages

    assert len(packages_after) - len(packages_before) == 1

    assert packages_after[0].name == "test-package"
    assert packages_after[1].name == "other-package"

def test_validate_packages(
    config,
    user,
    package_files,
    channel,
    channel_name,
    db,
    dao,
    pkgstore: PackageStore,
    package_filenames,
):
    user_id = user.id
    reindex_packages_from_store(dao, config, channel.name, user_id)
    db.refresh(channel)

    assert channel.packages
    assert channel.packages[0].name == "test-package"
    assert channel.packages[0].members[0].user.username == user.username
    assert (
        channel.packages[0].package_versions[0].version == "0.1"
        or channel.packages[0].package_versions[0].version == "0.2"
    )
    assert (
        channel.packages[0].package_versions[1].version == "0.1"
        or channel.packages[0].package_versions[1].version == "0.2"
    )

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata["packages"]) == 2
    assert set(repodata["packages"].keys()) == set(package_filenames)

    remaining_pkg = channel.packages[0].package_versions[1].filename
    pkgstore.delete_file(
        channel.name, f"linux-64/{channel.packages[0].package_versions[0].filename}"
    )

    validate_packages(dao, pkgstore, channel_name)

    db.refresh(channel)

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata["packages"]) == 1
    assert set(repodata["packages"].keys()) == set([remaining_pkg])
    assert len(channel.packages[0].package_versions) == 1

    pkgstore.add_file(b"wrong_size", channel_name, f"linux-64/{remaining_pkg}")

    validate_packages(dao, pkgstore, channel_name)

    db.refresh(channel)

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata["packages"]) == 0
    assert set(repodata["packages"].keys()) == set([])
    assert len(channel.packages[0].package_versions) == 0
