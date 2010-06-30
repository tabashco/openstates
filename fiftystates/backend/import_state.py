#!/usr/bin/env python
import glob

from fiftystates.backend import db

from saucebrush import run_recipe
from saucebrush.sources import JSONSource, MongoDBSource
from saucebrush.emitters import DebugEmitter, MongoDBEmitter, LoggingEmitter
from saucebrush.filters import (UnicodeFilter, UniqueIDValidator, FieldCopier,
                                SubrecordFilter, FieldAdder)

from fiftystates.backend.filters import (Keywordize, SplitName,
                                         LinkNIMSP, TimestampToDatetime,
                                         LinkVotesmart, RequireField,
                                         LegislatorIDValidator)


if __name__ == '__main__':
    import os
    import argparse
    import pymongo
    import logging
    from fiftystates import settings
    from fiftystates.backend.logs import init_mongo_logging
    from fiftystates.backend.utils import base_arg_parser, rotate_collections

    parser = argparse.ArgumentParser(parents=[base_arg_parser])

    parser.add_argument('--data_dir', '-d', type=str,
                        help='the base Fifty State data directory')

    args = parser.parse_args()

    if args.data_dir:
        data_dir = args.data_dir
    else:
        data_dir = settings.FIFTYSTATES_DATA_DIR

    db = pymongo.Connection().fiftystates

    init_mongo_logging()
    logger = logging.getLogger('fiftystates')
    logger.addHandler(logging.StreamHandler())

    metadata_path = os.path.join(data_dir, args.state, 'state_metadata.json')

    run_recipe(JSONSource(metadata_path),

               FieldCopier({'_id': 'abbreviation'}),

               LoggingEmitter(logger, "Importing metadata for %(_id)s"),
               MongoDBEmitter('fiftystates', 'metadata.temp'),
               )

    rotate_collections(args.state + '.bills')

    bills_path = os.path.join(data_dir, args.state, 'bills', '*.json')

    run_recipe(JSONSource(glob.iglob(bills_path)),

               UniqueIDValidator('state', 'session', 'chamber', 'bill_id'),
               Keywordize('title', '_keywords'),
               UnicodeFilter(),

               SubrecordFilter('sources', TimestampToDatetime('retrieved')),
               SubrecordFilter('actions', TimestampToDatetime('date')),
               SubrecordFilter('votes', TimestampToDatetime('date')),

               LoggingEmitter(logger, "Importing bill %(bill_id)s"),
               MongoDBEmitter('fiftystates', "%s.bills.current" % args.state),
               )

    rotate_collections(args.state + '.legislators')

    legislators_path = os.path.join(data_dir, args.state, 'legislators',
                                    '*.json')

    run_recipe(JSONSource(glob.iglob(legislators_path)),

               SplitName(),

               SubrecordFilter('roles', FieldAdder('state', args.state)),
               SubrecordFilter('roles', TimestampToDatetime('start_date')),
               SubrecordFilter('roles', TimestampToDatetime('end_date')),

               LinkNIMSP(),
               RequireField('nimsp_candidate_id'),
               LinkVotesmart(args.state),
               RequireField('votesmart_id'),
               LegislatorIDValidator(),

               LoggingEmitter(logger, "Importing legislator %(full_name)s"),
               MongoDBEmitter('fiftystates',
                              "%s.legislators.current" % args.state),
               )
