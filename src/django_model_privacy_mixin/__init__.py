'''
Created on 8 Mar.,2018

@author: Bernd Wechner
@status: Beta - works and is in use on a dedicated project.

In your Dango settings.py make sure to cilude 'crequest.middleware.CrequestMiddleware' in the MIDDDLEWARE list.

Provides one class PrivacyMixIn which adds Privacy support for model fields in a Django model.
'''

from django.core.exceptions import PermissionDenied
from django.forms.models import fields_for_model
from django.utils.safestring import mark_safe

from crequest.middleware import CrequestMiddleware

class PrivacyMixIn():
    '''
    A MixIn that adds database load overrides which populates the "hidden" attribute of
    an object with the names of fields that should be hidden. It is up to the other
    methods in the model to implement this hiding where desired.
    '''
    # The text to replace hidden fields with
    HIDDEN = mark_safe('<Hidden>')

    # A flag that we can set to enable or prevent replacing empty field values (None or empty string rep) with HIDDEN
    HIDE_EMPTY_FIELD = False

    # Configure the name of the atttribute we check of object ownership
    OWNER_FIELD = 'owner'

    # Configure the name of the method used to hide a field
    HIDE_METHOD = 'hide'

    def fields_to_hide(self, user):
        '''
        Given an object and a user (from request.user typically) will return a list of fields in that object
        that should be hidden. Does this by checking for any attributes in that object that are named visibility_*
        where * is the name of another attribute in the same object for which it specifies visibility rules by means
        of a bit flags. The the flags follow a naming convention as follows:

        all - all users can see the named field, namely it's a public piece of info. This is in fact the default
              for all fields that do not have a visibility_* partner. Having such a partner attribute with if no
              bit flags set will hide the field. Setting the all bit requests the default behaviour.

        all_* - all users who have an attribute * which is True can see this field.

        all_not_* - all users who have an attribute * which is False can see this field.

        share_* - all users who share some value in the * attribute. This is intended for memberships,
                  where * indicates one or more memberships of a user and of the object and if there's
                  an overlap the field will be visible. In an apocryphal case,* might be "group" and users
                  could be in one or more groups and objects could belong to one or more groups and if the
                  user and the object are both members of at least one group the field will be visible.
        '''
        def app_from_object(o):
            '''Given an object returns the name of the Django app that it's declared in'''
            return type(o).__module__.split('.')[0]

        def model_from_object(o):
            '''Given an object returns the name of the Django model that it is an instance of'''
            return o._meta.model.__name__

        def unique_object_id(o):
            if hasattr(o, "pk"):
                return "{}.{}.{}".format(app_from_object(o), model_from_object(o), o.pk)
            else:
                return None

        def get_User_extensions(user):
            '''
            Returns a list of attributes that are in request.user which represent User model extensions.
            That is have a OneToOne relationship with User.
            '''
            ext = []
            if not user is None and hasattr(user, 'is_authenticated'):
                if user.is_authenticated:
                    for field in user._meta.get_fields():
                        if field.one_to_one:
                            ext.append(field.name)
            return ext

        def get_User_membership(user, extensions, field_name):
            '''
            Given a user (from request.user, and extensions (from get_User_extensions) will check them for
            an attribute of field_name and for each one it finds will attempt to add its value or values
            to the membership set that it will return.
            '''
            membership = set()
            if hasattr(user, field_name):
                field = getattr(user, field_name, None)
                if hasattr(field, 'all') and callable(field.all):
                    membership.add((str(o) for o in field.all()))
                elif not field is None:
                    membership.add(str(field))

            for e in extensions:
                obj = getattr(user, e, None)
                if hasattr(obj, field_name):
                    field = getattr(obj, field_name)
                    if hasattr(field, 'all') and callable(field.all):
                        membership.update([unique_object_id(o) for o in field.all()])
                    elif not field is None:
                        membership.add(unique_object_id(field))

            return membership

        def get_User_flag(user, extensions, field_name):
            '''
            Given a user (from request.user, and extensions (from get_User_extensions) will check them for
            an attribute of field_name and if it's a bool return the value of the first one it finds. Gives
            priority to User model extensions but in no guaranteed order.
            '''
            for e in extensions:
                obj = getattr(user, e)
                if hasattr(obj, field_name):
                    field = getattr(obj, field_name)
                    if type(field) == bool:
                        return field

            if hasattr(user, field_name):
                field = getattr(user, field_name)
                if type(field) == bool:
                    return field

        def get_Owner(obj):
            '''
            A generic attempt to find an owner for the object passed. Basically checks the object for a field
            called owner which returns a user that is the objects owner. Simple really ;-) Best implemented as
            property in the model as in:

                @property
                def owner(self) -> User:
                    return <a field in the object that is of type "models.OneToOneField(User)>
            '''
            return getattr(obj, self.OWNER_FIELD, None)

        hide = []
        # if hasattr(self, 'visibility'):
        #     if isinstance(self.visibility, tuple):
        # Get the User model extensions (we'll check those for visibility tests)
        extensions = get_User_extensions(user)

        # We need attributes of the logged in user that the all_ and share_ flags can apply to.
        # Given the attribute we can look for it on:
        #    request.user
        #    request.user.player
        for field in self._meta.get_fields():
            prefix = 'visibility_'
            if field.name.startswith(prefix):
                rule_field = field
                look_field = field.name[len(prefix):]

                # Begin by assuming it is hidden
                hidden = True

                # Don't ever hide this field from an admin (superuser) or its owner, no tests needed
                if not user is None and ((hasattr(user, 'is_superuser') and user.is_superuser) or user == get_Owner(self)):
                    hidden = False
                else:
                    rule_flags = getattr(self, rule_field.name)
                    for flag in rule_flags:
                        if flag[1]: # flag is set
                            rule_name = flag[0]
                            if rule_name == 'all':
                                hidden = False # Don't hide this field for anyone, no tests needed
                            elif rule_name.startswith('all_'):
                                # hide this field from anyone who has not got True for the following field in the User (or False if not_)
                                target_value = True
                                check_field = rule_name[len('all_'):]
                                if check_field.startswith('not_'):
                                    check_field = check_field[len('not_'):]
                                    target_value = False

                                check_value = get_User_flag(user, extensions, check_field)

                                if check_value == target_value:
                                    hidden = False
                            elif rule_name.startswith('share_'):
                                # hide this field from anyone who has does not share one element in the following field
                                # This is for ManyToMany relations, essentially groups you may share membership of.
                                check_field = rule_name[len('share_'):]

                                if hasattr(self, check_field):
                                    # The logged in user's set of memberships
                                    usr_membership_set = get_User_membership(user, extensions, check_field)

                                    # The memberships of the object
                                    obj_membership_field = getattr(self, check_field, None)
                                    if obj_membership_field:
                                        if hasattr(obj_membership_field, 'all') and callable(obj_membership_field.all):
                                            obj_membership_set = set((unique_object_id(o) for o in obj_membership_field.all()))
                                        else:
                                            obj_membership_set = set(unique_object_id(obj_membership_field))

                                        if usr_membership_set.intersection(obj_membership_set):
                                            hidden = False

                                    # The memberships of the owner of the object (if exists)
                                    owner = get_Owner(self)
                                    if owner:
                                        own_membership_field = getattr(self, check_field, None)
                                        if own_membership_field:
                                            if hasattr(own_membership_field, 'all') and callable(own_membership_field.all):
                                                own_membership_set = set((unique_object_id(o) for o in own_membership_field.all()))
                                            else:
                                                own_membership_set = set(unique_object_id(own_membership_field))

                                        if usr_membership_set.intersection(own_membership_set):
                                            hidden = False

                if hidden:
                    hide.append(look_field)

        return hide

    def fields_for_model(self, *args, **kwargs):
        '''
        A replacement for django.forms.models.fields_for_model which respects privacy.

        Uses django.forms.models.fields_for_model and just removes hidden fields.

        This is what you should use in all forms that are going to display models that
        used the PrivacyMixIn.
        '''
        fields = fields_for_model(self._meta.model, *args, **kwargs)

        if hasattr(self,'hidden') and isinstance(self.hidden,  list):
            for f in self.hidden:
                if f in fields:
                    del fields[f]

        return fields

    @classmethod
    def from_db(cls, db, field_names, values):
        '''
        Override the from_db method.
        Runs the standard model from_db() then checks for and enforces privacy constraints.

        This is the central pinch point for database access and all requests for objects come
        through this method.
        '''
        obj = super().from_db(db, field_names, values)
        request = CrequestMiddleware.get_request()
        user = request.user
        obj.hidden = obj.fields_to_hide(user)
        if obj.hidden:
            for f in obj.hidden:
                val = getattr(obj, f, None)
                if cls.HIDE_EMPTY_FIELD or not (val is None or str(val) == ""):
                    if callable(getattr(obj, cls.HIDE_METHOD, None)):
                        setattr(obj, f, getattr(obj, cls.HIDE_METHOD)(cls._meta.get_field(f)))
                    else:
                        setattr(obj, f, cls.HIDDEN)
        return obj
