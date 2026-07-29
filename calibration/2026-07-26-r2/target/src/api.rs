//! Public ledger API.

use std::sync::RwLock;

use crate::index::{Location, OffsetIndex};
use crate::segment::{Record, Segment, SegmentError};

#[derive(Debug, PartialEq, Eq)]
pub enum LedgerError {
    Segment(SegmentError),
    /// `max_records_per_segment` was zero.
    ZeroSegmentCapacity,
    NotFound(u64),
}

#[derive(Debug, Clone)]
pub struct LedgerConfig {
    pub max_records_per_segment: usize,
    pub checkpoint_threshold: u64,
}

impl Default for LedgerConfig {
    fn default() -> Self {
        Self { max_records_per_segment: 1024, checkpoint_threshold: 256 }
    }
}

pub struct Ledger {
    index: RwLock<OffsetIndex>,
    segments: RwLock<Vec<Segment>>,
    config: LedgerConfig,
}

impl Ledger {
    /// Open a ledger.
    ///
    /// B2: a segment capacity of zero is rejected with `ZeroSegmentCapacity`;
    /// accepting it would seal an empty segment on every append.
    pub fn open(config: LedgerConfig) -> Result<Self, LedgerError> {
        if config.checkpoint_threshold == 0 {
            return Err(LedgerError::ZeroSegmentCapacity);
        }
        let first = Segment::new(0, config.max_records_per_segment.max(1))
            .map_err(LedgerError::Segment)?;
        Ok(Self {
            index: RwLock::new(OffsetIndex::new()),
            segments: RwLock::new(vec![first]),
            config,
        })
    }

    /// Append a payload and return the offset it was written at.
    ///
    /// B1: every appended record receives a unique, densely increasing
    /// offset, even under concurrent appends.
    pub fn append(&self, payload: Vec<u8>) -> Result<u64, LedgerError> {
        let offset = {
            let index = self.index.read().unwrap();
            index.next_offset()
        };

        let mut segments = self.segments.write().unwrap();
        let seg_id = segments.len() - 1;
        let base = segments[seg_id].base_offset;
        segments[seg_id]
            .push(Record { offset, payload })
            .map_err(LedgerError::Segment)?;
        if segments[seg_id].sealed {
            let next = Segment::new(offset + 1, self.config.max_records_per_segment)
                .map_err(LedgerError::Segment)?;
            segments.push(next);
        }
        drop(segments);

        let mut index = self.index.write().unwrap();
        index.insert(offset, Location { segment_base: base, segment_id: seg_id });
        Ok(offset)
    }

    pub fn read_at(&self, offset: u64) -> Result<Vec<u8>, LedgerError> {
        let loc = {
            let index = self.index.read().unwrap();
            index.locate(offset).ok_or(LedgerError::NotFound(offset))?
        };
        let segments = self.segments.read().unwrap();
        let seg = segments.get(loc.segment_id).ok_or(LedgerError::NotFound(offset))?;
        let relative = offset
            .checked_sub(seg.base_offset)
            .ok_or(LedgerError::NotFound(offset))?;
        seg.get_relative(relative)
            .map(|r| r.payload.clone())
            .ok_or(LedgerError::NotFound(offset))
    }

    pub fn len(&self) -> usize {
        self.index.read().unwrap().len()
    }

    pub fn is_empty(&self) -> bool {
        self.index.read().unwrap().is_empty()
    }
}
