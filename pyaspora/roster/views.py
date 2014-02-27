from flask import Blueprint, request, url_for

from pyaspora.contact.models import Contact
from pyaspora.contact.views import json_contact
from pyaspora.database import db
from pyaspora.user.session import require_logged_in_user
from pyaspora.user.views import json_user
from pyaspora.utils.rendering import abort, add_logged_in_user_to_data, \
    redirect, render_response
from pyaspora.utils.validation import post_param
from pyaspora.roster.models import Subscription, SubscriptionGroup

blueprint = Blueprint('roster', __name__, template_folder='templates')


@blueprint.route('/edit', methods=['GET'])
@require_logged_in_user
def view(_user):
    data = json_user(_user)

    friends = []
    subs = db.session.query(Subscription). \
        filter(Subscription.from_contact == _user.contact)
    for sub in subs:
        result = json_contact(sub.to_contact, _user)
        groups = sub.groups
        if groups:
            result['groups'] = [g.name for g in groups]
        friends.append(result)
    data['subscriptions'] = friends

    data['groups'] = [json_group(g, _user) for g in _user.groups]
    if 'actions' not in data:
        data['actions'] = {}
    data['actions']['create_group'] = \
        url_for('roster.create_group', _external=True)

    add_logged_in_user_to_data(data, _user)

    return render_response('roster_view.tpl', data)


def json_group(g, user):
    data = {
        'id': g.id,
        'name': g.name,
        'link': url_for('roster.view_group',
                            group_id=g.id, _external=True),
        'actions': {
            'delete': None,
            'rename': url_for('roster.rename_group',
                              group_id=g.id, _external=True)
        },
    }
    if not g.subscriptions:
        data['actions']['delete'] = url_for(
            'roster.delete_group', group_id=g.id, _external=True)
    return data


@blueprint.route('/groups/create', methods=['POST'])
@require_logged_in_user
def create_group(_user):
    name = post_param('name')

    db.session.add(SubscriptionGroup(user=_user, name=name))
    db.session.commit()

    return redirect(url_for('roster.view', _external=True))

@blueprint.route('/groups/<int:group_id>', methods=['GET'])
@require_logged_in_user
def view_group(group_id, _user):
    pass

@blueprint.route('/groups/<int:group_id>/edit', methods=['GET'])
@require_logged_in_user
def edit_group_form(group_id, _user):
    group = SubscriptionGroup.get(group_id)
    if not(group) or group.user_id != _user.id:
        abort(404, 'No such group')

    data = json_user(_user)

    data['actions'].update({
        'create_group': url_for('roster.create_group', _external=True),
        'move_contacts': url_for('roster.move_contacts', _external=True)
    })
    data.update({
        'group': json_group(group, _user),
        'other_groups': [json_group(g, _user)
                         for g in _user.groups if g.id != group.id]
    })

    add_logged_in_user_to_data(data, _user)

    return render_response('roster_edit_group.tpl', data)


@blueprint.route('/groups/<int:group_id>/rename', methods=['POST'])
@require_logged_in_user
def rename_group(group_id, _user):
    group = SubscriptionGroup.get(group_id)
    if not(group) or group.user_id != _user.id:
        abort(404, 'No such group')

    group.name = post_param('name')
    db.session.add(group)
    db.session.commit()

    return redirect(url_for('.view', _external=True))


@blueprint.route('/groups/<int:group_id>/delete', methods=['POST'])
@require_logged_in_user
def delete_group(group_id, _user):
    group = SubscriptionGroup.get(group_id)
    if not(group) or group.user_id != _user.id:
        abort(404, 'No such group')

    if group.subscriptions:
        abort(400, 'Only empty groups can be deleted')

    db.session.delete(group)
    db.session.commit()

    return redirect(url_for('.view', _external=True))


@blueprint.route('/contacts/<int:contact_id>/subscribe', methods=['POST'])
@require_logged_in_user
def subscribe(contact_id, _user):
    contact = Contact.get(contact_id)
    if not contact:
        abort(404, 'No such contact', force_status=True)

    _user.contact.subscribe(contact)

    db.session.commit()
    return redirect(url_for('contacts.profile', contact_id=contact.id))


@blueprint.route('/contacts/<int:contact_id>/unsubscribe', methods=['POST'])
@require_logged_in_user
def unsubscribe(contact_id, _user):
    contact = Contact.get(contact_id)
    if not contact:
        abort(404, 'No such contact', force_status=True)

    if not _user.contact.subscribed_to(contact):
        abort(400, 'Not subscribed')

    _user.contact.unsubscribe(contact)
    db.session.commit()
    return redirect(url_for('contacts.profile', contact_id=contact.id))


@blueprint.route('/contacts/move', methods=['POST'])
@require_logged_in_user
def move_contacts(_user):
    destination = post_param('destination')
    destination = SubscriptionGroup.get(destination)
    if not destination or destination.user_id != _user.id:
        abort(404, 'Destination not found')

    contacts = request.form.getlist('contact')
    if not contacts:
        abort(400, 'No contacts to move')

    contacts = [int(c) for c in contacts]

    subs = db.session.query(Subscription).join(SubscriptionGroup). \
        filter(Subscription.Queries.user_shares_for_contacts(
            _user, contacts))

    # Sigh - a direct update fails (on sqlite)
    for sub in subs:
        sub.group = destination
        db.session.add(sub)

    db.session.commit()

    return redirect(url_for('.view', _external=True))
