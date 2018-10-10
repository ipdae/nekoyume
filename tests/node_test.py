import datetime
import typing
import unittest.mock

from pytest import mark
from pytest_localserver.http import WSGIServer
from requests.exceptions import ConnectionError, Timeout
from requests_mock import Mocker, mock
from sqlalchemy.orm.scoping import scoped_session
from typeguard import typechecked

from nekoyume.models import Block, User
from nekoyume.node import Node


@typechecked
def test_node(fx_server: WSGIServer, fx_session: scoped_session):
    assert fx_server.url
    assert Node.get(fx_server.url, session=fx_session)
    assert Node.get(fx_server.url, session=fx_session).url == fx_server.url
    assert Node.get(fx_server.url, session=fx_session).last_connected_at


@typechecked
def test_broadcast(fx_session: scoped_session, fx_user: User):
    block = Block.create(fx_user, [])
    url = 'http://test.neko'
    now = datetime.datetime.utcnow()
    node = Node(url=url, last_connected_at=now)
    fx_session.add(node)
    fx_session.flush()
    with Mocker() as m:
        m.post(url, text='success')
        assert Node.broadcast(
            '',
            block.serialize(
                use_bencode=False,
                include_suffix=True,
                include_moves=True,
                include_hash=True
            )
        ) is True
        assert node.last_connected_at > now


@typechecked
def test_broadcast_my_node(fx_session: scoped_session, fx_user: User):
    block = Block.create(fx_user, [])
    url = 'http://test.neko'
    now = datetime.datetime.utcnow()
    node = Node(url=url, last_connected_at=now)
    fx_session.add(node)
    fx_session.flush()
    with unittest.mock.patch('nekoyume.node.post') as m:
        expected = serialized = block.serialize(
            use_bencode=False,
            include_suffix=True,
            include_moves=True,
            include_hash=True
        )
        assert Node.broadcast('', serialized, my_node=node) is True
        expected['sent_node'] = url
        assert node.last_connected_at > now
        m.assert_called_once_with(url + '', json=expected, timeout=3)


@typechecked
def test_broadcast_same_node(fx_session: scoped_session, fx_user: User):
    block = Block.create(fx_user, [])
    url = 'http://test.neko'
    now = datetime.datetime.utcnow()
    node = Node(url=url, last_connected_at=now)
    fx_session.add(node)
    fx_session.flush()
    assert Node.broadcast(
        '',
        block.serialize(
            use_bencode=False,
            include_suffix=True,
            include_moves=True,
            include_hash=True
        ),
        sent_node=node
    ) is True
    assert node.last_connected_at == now


@mark.parametrize('error', [ConnectionError, Timeout])
def test_broadcast_raise_exception(
        fx_session: scoped_session, fx_user: User,
        error: typing.Union[ConnectionError, Timeout]
):
    block = Block.create(fx_user, [])
    url = 'http://test.neko'
    now = datetime.datetime.utcnow()
    node = Node(url=url, last_connected_at=now)
    fx_session.add(node)
    fx_session.flush()
    with Mocker() as m:
        m.post(url, exc=error)
        assert Node.broadcast(
            '',
            block.serialize(
                use_bencode=False,
                include_suffix=True,
                include_moves=True,
                include_hash=True
            )
        ) is True
        assert node.last_connected_at == now


def test_node_broadcast_retry(fx_session: scoped_session,
                              fx_user: User):
    block = Block.create(fx_user, [])
    url = 'http://test.neko'
    now = datetime.datetime.utcnow()
    node = Node(url=url, last_connected_at=now)
    fx_session.add(node)
    fx_session.flush()
    with mock() as m:
        m.register_uri('POST', url, [
            {
                'json': {
                    'result': 'failed',
                    'block_id': 0,
                    'mesage': "new block isn't our next block."
                },
                'status_code': 403
            },
            {
                'json': {
                    'result': 'success',
                },
                'status_code': 200
            }
        ])
        assert Node.broadcast(
            '',
            block.serialize(
                use_bencode=False,
                include_suffix=True,
                include_moves=True,
                include_hash=True
            )
        ) is True
        assert m.call_count == 2
        assert node.last_connected_at > now
