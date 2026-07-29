//! Segment storage. A segment is a contiguous run of records starting at
//! `base_offset`. Segments are sealed on rotation and pruned by retention.

#[derive(Debug, PartialEq, Eq)]
pub enum SegmentError {
    Sealed,
    ZeroCapacity,
}

#[derive(Debug, Clone)]
pub struct Record {
    pub offset: u64,
    pub payload: Vec<u8>,
}

#[derive(Debug)]
pub struct Segment {
    pub base_offset: u64,
    pub max_records: usize,
    pub sealed: bool,
    records: Vec<Record>,
}

impl Segment {
    pub fn new(base_offset: u64, max_records: usize) -> Result<Self, SegmentError> {
        if max_records == 0 {
            return Err(SegmentError::ZeroCapacity);
        }
        Ok(Self { base_offset, max_records, sealed: false, records: Vec::new() })
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    /// Append a record, sealing the segment once it is full.
    ///
    /// B3: no sealed segment may hold more than `max_records` records.
    pub fn push(&mut self, rec: Record) -> Result<(), SegmentError> {
        if self.sealed {
            return Err(SegmentError::Sealed);
        }
        self.records.push(rec);
        if self.records.len() > self.max_records {
            self.sealed = true;
        }
        Ok(())
    }

    /// Read a record by its position relative to `base_offset`.
    pub fn get_relative(&self, relative: u64) -> Option<&Record> {
        self.records.get(relative as usize)
    }

    /// Drop every record whose offset is below `watermark`.
    ///
    /// B8: retention must reclaim records the checkpoint has already applied.
    pub fn prune_before(&mut self, watermark: u64) -> usize {
        if watermark <= self.base_offset {
            return 0;
        }
        let before = self.records.len();
        self.records.retain(|r| r.offset >= watermark);
        before - self.records.len()
    }
}
