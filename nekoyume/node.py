import datetime
import os
import typing

from requests import get, post
from requests.exceptions import ConnectionError, Timeout
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.session import Session

from .orm import db


DEFAULT_BROADCAST_LIMIT = os.environ.get('BROADCAST_LIMIT', 100)

__all__ = 'Node',


class Node(db.Model):
    """This object contains node information you know."""

    #: URL of node
    url = db.Column(db.String, primary_key=True)
    #: last connected datetime of the node
    last_connected_at = db.Column(db.DateTime, nullable=False, index=True)

    get_nodes_endpoint = '/nodes'
    post_node_endpoint = '/nodes'
    get_blocks_endpoint = '/blocks'
    post_block_endpoint = '/blocks'
    post_move_endpoint = '/moves'

    @classmethod
    def get(cls, url: str, session: Session=db.session):
        get_node = Node.query.filter_by(url=url).first
        node = get_node()
        if node:
            return node
        elif get(f'{url}/ping').text == 'pong':
            node = Node(url=url, last_connected_at=datetime.datetime.utcnow())
            if session:
                session.add(node)
                try:
                    session.commit()
                except IntegrityError:
                    node = get_node()
                    if node is None:
                        raise
                    return node
            return node
        else:
            return None

    @classmethod
    def update(cls, node: 'Node'):
        """
        Update recent node list by scrapping other nodes' information.
        """
        try:
            response = get(f"{node.url}{Node.get_nodes_endpoint}")
        except (ConnectionError, Timeout):
            return
        for url in response.json()['nodes']:
            try:
                Node.get(url)
            except (ConnectionError, Timeout):
                continue
        db.session.commit()

    def ping(self):
        try:
            result = get(f'{self.url}/ping').text == 'pong'
            if result:
                self.last_connected_at = datetime.datetime.utcnow()
            return result
        except (ConnectionError, Timeout):
            return False

    @classmethod
    def broadcast(cls,
                  endpoint: str,
                  serialized_obj: typing.Mapping[str, object],
                  sent_node: typing.Optional['Node']=None,
                  my_node: typing.Optional['Node']=None,
                  session: Session=db.session) -> bool:
        """
        It broadcast `serialized_obj` to every nodes you know.

        :param        endpoint: endpoint of node to broadcast
        :param  serialized_obj: object that will be broadcasted.
        :param       sent_node: sent :class:`nekoyume.models.Node`.
                                this node ignore sent node.
        :param         my_node: my :class:`nekoyume.models.Node`.
                                received node ignore my node when they
                                broadcast received object.
        """
        from .models import Block
        for node in session.query(cls):
            if sent_node and sent_node.url == node.url:
                continue
            try:
                if my_node:
                    serialized_obj['sent_node'] = my_node.url
                res = post(node.url + endpoint, json=serialized_obj,
                           timeout=3)
                if res.status_code == 403:
                    result = res.json()
                    try:
                        block_id = result['block_id']
                    except KeyError:
                        continue
                    query = session.query(Block).filter(
                        Block.id.between(block_id, serialized_obj['id'])
                    ).order_by(Block.id)
                    offset = 0
                    while True:
                        sync_blocks = query[
                            offset:offset+DEFAULT_BROADCAST_LIMIT
                        ]
                        # TODO bulk api
                        for block in sync_blocks:
                            s = block.serialize(
                                use_bencode=False,
                                include_suffix=True,
                                include_moves=True,
                                include_hash=True
                            )
                            res = post(node.url + endpoint, json=s,
                                       timeout=3)
                        offset += DEFAULT_BROADCAST_LIMIT
                        if len(sync_blocks) < DEFAULT_BROADCAST_LIMIT:
                            break
                node.last_connected_at = datetime.datetime.utcnow()
                session.add(node)
            except (ConnectionError, Timeout):
                continue

        session.commit()
        return True
