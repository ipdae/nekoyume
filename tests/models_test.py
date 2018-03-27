import datetime

import pytest

from nekoyume.models import (Block,
                             CreateNovice,
                             HackAndSlash,
                             LevelUp,
                             Move,
                             Node,
                             Say,
                             Send,
                             Sleep,
                             User)


@pytest.fixture
def fx_user2(fx_session):
    user = User('test2')
    user.session = fx_session
    return user


@pytest.fixture
def fx_other_user(fx_other_session):
    user = User('other_test')
    user.session = fx_other_session
    return user


@pytest.fixture
def fx_novice_status():
    return {
        'strength': '15',
        'dexterity': '12',
        'constitution': '16',
        'intelligence': '9',
        'wisdom': '8',
        'charisma': '13'}


def test_move_confirmed_and_validation(fx_user, fx_novice_status):
    move = Move()
    assert not move.confirmed
    assert not move.valid

    move = fx_user.create_novice(fx_novice_status)

    assert not move.confirmed
    assert move.valid

    block = fx_user.create_block([move])

    assert move.block_id
    assert move.confirmed
    assert move.valid

    move.tax = 1
    assert not move.valid
    assert not block.valid


def test_level_up(fx_user, fx_novice_status):
    move = fx_user.create_novice(fx_novice_status)
    fx_user.create_block([move])

    while True:
        if fx_user.avatar().xp >= 8:
            break
        move = fx_user.hack_and_slash()
        fx_user.create_block([move])

        if fx_user.avatar().hp <= 0:
            move = fx_user.sleep()
            fx_user.create_block([move])

    prev_strength = fx_user.avatar().strength
    prev_xp = fx_user.avatar().xp
    move = fx_user.level_up('strength')
    fx_user.create_block([move])

    assert fx_user.avatar().lv == 2
    assert fx_user.avatar().xp == prev_xp - 8
    assert fx_user.avatar().strength == prev_strength + 1


def test_send(fx_user, fx_user2, fx_novice_status):
    move = fx_user.create_novice(fx_novice_status)
    move2 = fx_user2.create_novice(fx_novice_status)
    block = fx_user.create_block([move, move2])

    assert fx_user.avatar(block.id).items['Gold'] == 8

    move = fx_user.move(Send(details={
        'item_name': 'Gold',
        'amount': 1,
        'receiver': fx_user2.address}))
    block = fx_user.create_block([move])

    assert fx_user.avatar(block.id).items['Gold'] == 15
    assert fx_user2.avatar(block.id).items['Gold'] == 1


def test_block_validation(fx_user, fx_novice_status):
    move = fx_user.create_novice(fx_novice_status)
    block = fx_user.create_block([move])
    assert block.valid
    move.id = ('00000000000000000000000000000000'
               '00000000000000000000000000000000')
    assert not block.valid


def test_avatar_modifier(fx_user, fx_novice_status):
    move = fx_user.create_novice(fx_novice_status)
    fx_user.create_block([move])
    assert fx_user.avatar().modifier('constitution') == 2
    assert fx_user.avatar().modifier('strength') == 1
    assert fx_user.avatar().modifier('dexterity') == 0
    assert fx_user.avatar().modifier('wisdom') == -1


def test_avatar_basic_moves(fx_user, fx_novice_status):
    moves = [
        CreateNovice(details=fx_novice_status),
        HackAndSlash(),
        Sleep(),
        Say(details={'content': 'hi'}),
        LevelUp(details={'new_status': 'strength'}),
    ]
    for move in moves:
        move = fx_user.move(move)
        block = fx_user.create_block([move])
        assert move.valid
        assert move.confirmed
        assert block.valid
        assert fx_user.avatar(block.id)


def test_sync(fx_user, fx_session, fx_other_user, fx_other_session, fx_server,
              fx_novice_status):
    assert fx_other_session.query(Block).count() == 0
    assert fx_session.query(Block).count() == 0

    Block.sync(Node(url=fx_server.url), fx_other_session)
    assert fx_other_session.query(Block).count() == 0
    assert fx_session.query(Block).count() == 0

    fx_other_user.create_block([])
    Block.sync(Node(url=fx_server.url), fx_other_session)
    assert fx_other_session.query(Block).count() == 1
    assert fx_session.query(Block).count() == 0

    move = fx_user.create_novice(fx_novice_status)
    fx_user.create_block([move])
    fx_user.create_block([])
    fx_user.create_block([])

    assert fx_other_session.query(Block).count() == 1
    assert fx_other_session.query(Move).count() == 0
    assert fx_session.query(Block).count() == 3
    assert fx_session.query(Move).count() == 1

    Block.sync(Node(url=fx_server.url), fx_other_session)
    assert fx_other_session.query(Block).count() == 3
    assert fx_other_session.query(Move).count() == 1
    assert fx_session.query(Block).count() == 3
    assert fx_session.query(Move).count() == 1


def test_block_broadcast(fx_user, fx_session, fx_other_user, fx_other_session,
                         fx_server):
    assert fx_other_session.query(Block).count() == 0
    assert fx_session.query(Block).count() == 0

    fx_other_session.add(Node(url=fx_server.url,
                              last_connected_at=datetime.datetime.now()))
    fx_other_session.commit()

    block = fx_other_user.create_block([])
    block.broadcast(session=fx_other_session)
    assert fx_other_session.query(Block).count() == 1
    assert fx_session.query(Block).count() == 1


def test_move_broadcast(fx_user, fx_session, fx_other_user, fx_other_session,
                        fx_server, fx_novice_status):
    assert fx_other_session.query(Move).count() == 0
    assert fx_session.query(Move).count() == 0

    fx_other_session.add(Node(url=fx_server.url,
                              last_connected_at=datetime.datetime.now()))
    fx_other_session.commit()

    move = fx_other_user.create_novice(fx_novice_status)
    assert not fx_session.query(Move).get(move.id)

    move.broadcast(session=fx_other_session)
    assert fx_session.query(Move).get(move.id)