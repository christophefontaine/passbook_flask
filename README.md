![Passbook](http://cl.ly/JPjc/title_passbook.png)

[![Build Status](https://travis-ci.org/lithammer/passbook_flask_example.png)](https://travis-ci.org/lithammer/passbook_flask_example)

# Passbook on Flask Example

[Passbook](http://www.apple.com/ios/whats-new/#passbook) is an iOS 6 feature
that manages boarding passes, movie tickets, retail coupons, & loyalty cards.
Using the [PassKit API](https://developer.apple.com/library/prerelease/ios/#documentation/UserExperience/Reference/PassKit_Framework/_index.html),
developers can register web services to automatically update content on the
pass, such as gate changes on a boarding pass, or adding credit to a loyalty
card.

Apple [provides a specification](https://developer.apple.com/library/prerelease/ios/#documentation/PassKit/Reference/PassKit_WebService/WebService.html) for a REST-style web service protocol to communicate with Passbook, with endpoints to get the latest version of a pass, register / unregister devices to receive push notifications for a pass, and query for passes registered for a device.

This project is an example implementation of this web service specification in Flask.

> Apple recently updated their Developer Program License Agreement, so if you
> have an active developer account, but cannot access the links to PassKit
> documentation, make sure that you've accepted the new terms. You can accept
> the new terms on the main page of the iOS Member Center.

## Requirements

- Python 3
- sqlite

## Getting Started

```bash
$ git clone https://github.com/christophefontaine/passbook_flask passbook
$ cd passbook
$ python app.py
```


---

## Specification

What follows is a summary of the specification. The complete specification can
be found in the [Passbook Web Service Reference](https://developer.apple.com/library/prerelease/ios/#documentation/PassKit/Reference/PassKit_WebService/WebService.html).

### Getting the Latest Version of a Pass

```
GET http://example.com/passes/<pass_type_identifier>/<serial_number>
```

- **pass_type_identifier** The pass’s type, as specified in the pass.
- **serial_number** The unique pass identifier, as specified in the pass.

**Response**

- If request is authorized, return HTTP status 200 with a payload of the pass data.
- If the request is not authorized, return HTTP status 401.
- Otherwise, return the appropriate standard HTTP status.

### Getting the Serial Numbers for Passes Associated with a Device

```
GET http://example.com/devices/<device_library_identifier>/registrations/<pass_type_identifier>[?passesUpdatedSince=tag]
```

- **device_library_identifier** A unique identifier that is used to identify and authenticate the device.
- **pass_type_identifier** The pass’s type, as specified in the pass.
- **serial_number** The unique pass identifier, as specified in the pass.
- **passesUpdatedSince** _(optional)_ A tag from a previous request.

**Response**

If the `passesUpdatedSince` parameter is present, return only the passes that
have been updated since the time indicated by tag. Otherwise, return all
passes.

- If there are matching passes, return HTTP status 200 with a JSON dictionary with the following keys and values:
    - **last_updated** _(string)_ The current modification tag.
    - **serial_numbers** _(array of strings)_ The serial numbers of the matching passes.
- If there are no matching passes, return HTTP status 204.
- Otherwise, return the appropriate standard HTTP status.

### Registering a Device to Receive Push Notifications for a Pass

```
POST http://example.com/devices/<device_library_identifier>/registrations/<pass_type_identifier>/<serial_number>
```

- **device_library_identifier** A unique identifier that is used to identify and authenticate the device.
- **pass_type_identifier** The pass’s type, as specified in the pass.
- **serial_number** The unique pass identifier, as specified in the pass.

The POST payload is a JSON dictionary, containing a single key and value:

- **push_token** The push token that the server can use to send push notifications to this device.

**Response**

- If the serial number is already registered for this device, return HTTP status 200.
- If registration succeeds, return HTTP status 201.
- If the request is not authorized, return HTTP status 401.
- Otherwise, return the appropriate standard HTTP status.

### Unregistering a Device

```
DELETE http://example.com/devices/<device_library_identifier>/registrations/<pass_type_identifier>/<serial_number>
```

- **device_library_identifier** A unique identifier that is used to identify and authenticate the device.
- **pass_type_identifier** The pass’s type, as specified in the pass.
- **serial_number** The unique pass identifier, as specified in the pass.

**Response**

- If disassociation succeeds, return HTTP status 200.
- If the request is not authorized, return HTTP status 401.
- Otherwise, return the appropriate standard HTTP status.

---

## Contact
Based on the code from Peter Lithammer
- [https://github.com/lithammer](https://github.com/lithammer)

- [https://github.com/christophefontaine](https://github.com/christophefontaine)

## License

passbook_flask_example is available under the MIT license. See the LICENSE file
for more info.
